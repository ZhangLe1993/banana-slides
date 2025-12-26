"""
Gemini Inpainting 消除服务提供者
使用 Gemini 2.5 Flash Image Preview 模型进行基于 mask 的图像编辑
"""
import logging
from typing import Optional
from PIL import Image
from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_config

logger = logging.getLogger(__name__)


class GeminiInpaintingProvider:
    """Gemini Inpainting 消除服务（使用 Gemini 2.5 Flash）"""
    
    DEFAULT_MODEL = "gemini-2-5-flash-image-preview"
    DEFAULT_PROMPT = (
        "1.Remove all text content; keep only the outermost rectangular frames and arrows (if any).\n"
        "2.Keep the layout unchanged.\n"
        "3.Change the background color to white."
    )
    
    def __init__(
        self, 
        api_key: str, 
        api_base: str = None,
        model: str = None,
        timeout: int = 60
    ):
        """
        初始化 Gemini Inpainting 提供者
        
        Args:
            api_key: Google API key
            api_base: API base URL (for proxies like aihubmix)
            model: Model name to use (default: gemini-2-5-flash-image-preview)
            timeout: API 请求超时时间（秒）
        """
        self.api_key = api_key
        self.api_base = api_base
        self.model = model or self.DEFAULT_MODEL
        self.timeout = timeout
        
        timeout_ms = int(timeout * 1000)
        
        # 构建 HttpOptions
        http_options = types.HttpOptions(
            base_url=api_base,
            timeout=timeout_ms
        ) if api_base else types.HttpOptions(timeout=timeout_ms)
        
        self.client = genai.Client(
            http_options=http_options,
            api_key=api_key
        )
        
        logger.info(f"✅ Gemini Inpainting Provider 初始化 (model={self.model})")
    
    @retry(
        stop=stop_after_attempt(3),  # 最多重试3次
        wait=wait_exponential(multiplier=1, min=2, max=10),  # 指数避让: 2s, 4s, 8s
        reraise=True
    )
    def inpaint_image(
        self,
        original_image: Image.Image,
        mask_image: Image.Image,
        inpaint_mode: str = "remove",
        custom_prompt: Optional[str] = None
    ) -> Optional[Image.Image]:
        """
        使用 Gemini 和掩码进行图像编辑
        
        Args:
            original_image: 原始图像
            mask_image: 掩码图像（白色=消除，黑色=保留）
            inpaint_mode: 修复模式（未使用，保留兼容性）
            custom_prompt: 自定义 prompt（如果为 None 则使用默认）
            
        Returns:
            处理后的图像，失败返回 None
        """
        try:
            logger.info("🚀 开始调用 Gemini inpainting")
            
            # 1. 转换图像格式
            # 原图转换为 RGB
            if original_image.mode in ('RGBA', 'LA', 'P'):
                if original_image.mode == 'RGBA':
                    background = Image.new('RGB', original_image.size, (255, 255, 255))
                    background.paste(original_image, mask=original_image.split()[3])
                    original_image = background
                else:
                    original_image = original_image.convert('RGB')
            
            # Mask 转换为 RGB（Gemini 需要）
            # 注意：Gemini 的 mask 约定可能与火山引擎不同
            # 火山：黑色=保留，白色=消除
            # Gemini：需要测试，可能需要反转
            if mask_image.mode != 'RGB':
                # 转换灰度图为RGB
                mask_rgb = Image.new('RGB', mask_image.size)
                if mask_image.mode == 'L':
                    mask_rgb = Image.merge('RGB', (mask_image, mask_image, mask_image))
                else:
                    mask_rgb = mask_image.convert('RGB')
                mask_image = mask_rgb
            
            logger.info(f"📷 图像尺寸: 原图={original_image.size}, mask={mask_image.size}")
            
            # 2. 构建 prompt
            prompt = custom_prompt or self.DEFAULT_PROMPT
            logger.info(f"📝 Prompt: {prompt[:100]}...")
            
            # 3. 构建请求内容
            # 根据 Gemini 文档，image editing 需要同时提供原图和 mask
            contents = [
                original_image,
                mask_image,
                prompt
            ]
            
            logger.info("🌐 发送请求到 Gemini API...")
            
            # 4. 调用 Gemini API
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=['IMAGE'],  # 只需要图像输出
                    image_config=types.ImageConfig(
                        aspect_ratio="free",  # 保持原始比例
                        image_size="ORIGINAL"  # 保持原始尺寸
                    ),
                )
            )
            
            logger.debug("Gemini API 调用完成")
            
            # 5. 提取生成的图像
            for i, part in enumerate(response.parts):
                if part.text is not None:
                    logger.debug(f"Part {i}: TEXT - {part.text[:100]}")
                else:
                    try:
                        logger.debug(f"Part {i}: 尝试提取图像...")
                        result_image = Image.open(part.inline_data.to_bytes_io())
                        logger.info(f"✅ Gemini Inpainting 成功！结果: {result_image.size}, {result_image.mode}")
                        return result_image
                    except Exception as e:
                        logger.debug(f"Part {i}: 不是有效图像 - {e}")
                        continue
            
            logger.error("❌ 响应中未找到图像")
            return None
            
        except Exception as e:
            logger.error(f"❌ Gemini Inpainting 失败: {e}", exc_info=True)
            raise

