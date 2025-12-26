"""
Gemini Inpainting 消除服务提供者
使用 Gemini 2.5 Flash Image Preview 模型进行基于 mask 的图像编辑
"""
import logging
from typing import Optional
from PIL import Image
from google import genai
from google.genai import types
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    wait_fixed,
    retry_if_result
)
from config import get_config

logger = logging.getLogger(__name__)


class GeminiInpaintingProvider:
    """Gemini Inpainting 消除服务（使用 Gemini 2.5 Flash）"""
    
    DEFAULT_MODEL = "gemini-2.5-flash-image-preview"
    DEFAULT_PROMPT = (
        "Based on the original image and the mask (white areas indicate regions to remove), "
        "please remove all text and graphic content within the masked regions to create a clean background. "
        "The resulting background should maintain the same style and be visually consistent with the original image. "
        "Keep the layout structure unchanged."
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
            model: Model name to use (default: gemini-2.5-flash-image-preview)
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
    
    def _expand_to_16_9(self, image: Image.Image, fill_color=(255, 255, 255)) -> tuple[Image.Image, tuple[int, int, int, int]]:
        """
        将图像扩展到 16:9 比例（Gemini 要求标准比例）
        
        Args:
            image: 原始图像
            fill_color: 填充颜色（默认白色）
            
        Returns:
            (扩展后的图像, 原图在扩展图中的位置 (x0, y0, x1, y1))
        """
        original_width, original_height = image.size
        
        # 计算16:9比例下的目标尺寸
        target_ratio = 16 / 9
        current_ratio = original_width / original_height
        
        if abs(current_ratio - target_ratio) < 0.01:
            # 已经是16:9，不需要扩展
            return image, (0, 0, original_width, original_height)
        
        if current_ratio > target_ratio:
            # 宽度足够，需要增加高度
            target_width = original_width
            target_height = int(original_width / target_ratio)
        else:
            # 高度足够，需要增加宽度
            target_height = original_height
            target_width = int(original_height * target_ratio)
        
        # 创建16:9画布
        expanded = Image.new('RGB', (target_width, target_height), fill_color)
        
        # 将原图居中粘贴
        x_offset = (target_width - original_width) // 2
        y_offset = (target_height - original_height) // 2
        expanded.paste(image, (x_offset, y_offset))
        
        # 返回扩展后的图像和原图位置
        crop_box = (x_offset, y_offset, x_offset + original_width, y_offset + original_height)
        
        logger.info(f"📐 扩展图像: {original_width}x{original_height} -> {target_width}x{target_height} (16:9)")
        logger.info(f"   原图位置: {crop_box}")
        
        return expanded, crop_box
    
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
        custom_prompt: Optional[str] = None,
        full_page_image: Optional[Image.Image] = None,
        crop_box: Optional[tuple] = None
    ) -> Optional[Image.Image]:
        """
        使用 Gemini 和掩码进行图像编辑
        
        Args:
            original_image: 原始图像
            mask_image: 掩码图像（白色=消除，黑色=保留）
            inpaint_mode: 修复模式（未使用，保留兼容性）
            custom_prompt: 自定义 prompt（如果为 None 则使用默认）
            full_page_image: 完整的 PPT 页面图像（16:9），如果提供则直接使用
            crop_box: 裁剪框 (x0, y0, x1, y1)，指定从完整页面结果中裁剪的区域
            
        Returns:
            处理后的图像，失败返回 None
        """
        try:
            logger.info("🚀 开始调用 Gemini inpainting")
            
            # 保存 original_image 的尺寸（用于最终裁剪）
            target_size = original_image.size
            
            # 判断使用哪个图像
            if full_page_image is not None:
                # 使用完整的 PPT 页面图像（16:9）
                logger.info("📄 使用完整 PPT 页面图像（16:9）")
                use_full_page = True
                working_image = full_page_image
                original_size = full_page_image.size
                
                # 如果没有提供 crop_box，通过 mask 的位置推断
                if crop_box is None:
                    # 假设 mask 的尺寸就是 original_image 的尺寸
                    # 需要找到 mask 在完整页面中的位置
                    logger.warning("⚠️ 未提供 crop_box，将使用 original_image 的尺寸作为裁剪区域")
                    # 这里暂时返回完整图像，实际应该提供 crop_box
            else:
                # 使用传入的 original_image 并扩展到 16:9
                logger.info("📄 使用传入图像并扩展到 16:9")
                use_full_page = False
                working_image = original_image
                original_size = original_image.size
            
            # 1. 转换图像格式
            # 原图转换为 RGB
            if working_image.mode in ('RGBA', 'LA', 'P'):
                if working_image.mode == 'RGBA':
                    background = Image.new('RGB', working_image.size, (255, 255, 255))
                    background.paste(working_image, mask=working_image.split()[3])
                    working_image = background
                else:
                    working_image = working_image.convert('RGB')
            
            # Mask 转换为 RGB（Gemini 需要）
            if mask_image.mode != 'RGB':
                # 转换灰度图为RGB
                if mask_image.mode == 'L':
                    mask_image = Image.merge('RGB', (mask_image, mask_image, mask_image))
                else:
                    mask_image = mask_image.convert('RGB')
            
            # 2. 如果使用完整页面图像，需要扩展 mask 到完整页面大小
            result_crop_box = crop_box  # 保存传入的 crop_box
            
            if use_full_page:
                # 直接使用完整页面图像
                final_image = working_image
                
                # 扩展 mask 到完整页面大小
                if crop_box:
                    # 创建与完整页面同样大小的黑色 mask
                    full_mask = Image.new('RGB', final_image.size, (0, 0, 0))
                    # 将原 mask 粘贴到正确的位置
                    x0, y0, x1, y1 = crop_box
                    # 确保 mask 尺寸匹配
                    mask_resized = mask_image.resize((x1 - x0, y1 - y0), Image.LANCZOS)
                    full_mask.paste(mask_resized, (x0, y0))
                    final_mask = full_mask
                    logger.info(f"📷 完整页面模式: 页面={final_image.size}, mask扩展到={final_mask.size}, 粘贴位置={crop_box}")
                else:
                    # 没有 crop_box，假设 mask 已经是正确大小
                    final_mask = mask_image
                    logger.warning(f"⚠️ 完整页面模式但没有 crop_box，直接使用 mask: {final_mask.size}")
            else:
                # 扩展到 16:9 比例（Gemini 要求）
                final_image, expand_crop_box = self._expand_to_16_9(working_image, fill_color=(255, 255, 255))
                final_mask, _ = self._expand_to_16_9(mask_image, fill_color=(0, 0, 0))  # mask用黑色填充
                result_crop_box = expand_crop_box  # 使用扩展后的 crop_box
                logger.info(f"📷 图像尺寸: 原图={original_size}, 扩展后={final_image.size}")
            
            # 3. 构建 prompt
            prompt = custom_prompt or self.DEFAULT_PROMPT
            logger.info(f"📝 Prompt: {prompt[:100]}...")
            
            # 4. 构建请求内容
            # 根据 Gemini 文档，image editing 需要同时提供原图和 mask
            # 直接传递 PIL Image 对象和文本，SDK 会自动处理
            contents = [
                final_image,
                final_mask,
                prompt
            ]
            
            logger.info("🌐 发送请求到 Gemini API (stream)...")
            
            # 5. 调用 Gemini API (使用 stream)
            generate_content_config = types.GenerateContentConfig(
                response_modalities=['IMAGE', 'TEXT'],
                image_config=types.ImageConfig(
                    aspect_ratio="16:9",  # 使用16:9比例
                ),
            )
            
            # 6. 提取生成的图像并裁剪回原始尺寸
            from io import BytesIO
            
            for chunk in self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=generate_content_config,
            ):
                # 检查是否有有效的候选响应
                if (
                    chunk.candidates is None
                    or chunk.candidates[0].content is None
                    or chunk.candidates[0].content.parts is None
                ):
                    continue
                
                # 检查是否有图像数据
                part = chunk.candidates[0].content.parts[0]
                if part.inline_data and part.inline_data.data:
                    logger.debug("✅ 找到图像数据")
                    try:
                        # 从 inline_data.data 读取图像
                        image_data = part.inline_data.data
                        result_image = Image.open(BytesIO(image_data))
                        logger.info(f"✅ Gemini Inpainting 成功！结果尺寸: {result_image.size}, {result_image.mode}")
                        
                        # 根据是否使用完整页面决定是否裁剪
                        if use_full_page:
                            # 使用完整页面，需要裁剪出 original_image 对应的区域
                            if result_crop_box:
                                cropped_result = result_image.crop(result_crop_box)
                                logger.info(f"✂️  从完整页面裁剪: {result_image.size} -> {cropped_result.size}")
                                return cropped_result
                            else:
                                # 没有 crop_box，返回完整结果（不推荐）
                                logger.warning(f"⚠️ 没有 crop_box，返回完整页面: {result_image.size}")
                                return result_image
                        else:
                            # 扩展模式，裁剪回原始尺寸
                            cropped_result = result_image.crop(result_crop_box)
                            logger.info(f"✂️  裁剪回原始尺寸: {cropped_result.size}")
                            return cropped_result
                    except Exception as e:
                        logger.error(f"解析图像数据失败: {e}")
                        continue
                elif chunk.text:
                    logger.debug(f"收到文本: {chunk.text[:100]}")
            
            logger.error("❌ 响应中未找到图像")
            return None
            
        except Exception as e:
            logger.error(f"❌ Gemini Inpainting 失败: {e}", exc_info=True)
            raise
    
    def inpaint_with_retry(
        self,
        original_image: Image.Image,
        mask_image: Image.Image,
        max_retries: int = 2,
        retry_delay: int = 1,
        full_page_image: Optional[Image.Image] = None,
        crop_box: Optional[tuple] = None
    ) -> Optional[Image.Image]:
        """
        带重试的 inpaint 调用（使用 tenacity 库）
        
        Args:
            original_image: 原始图像
            mask_image: 掩码图像
            max_retries: 最大重试次数（包括首次尝试）
            retry_delay: 重试延迟（秒）
            full_page_image: 完整的 PPT 页面图像（16:9），如果提供则直接使用
            crop_box: 裁剪框 (x0, y0, x1, y1)，从完整页面结果中裁剪的区域
            
        Returns:
            处理后的图像，失败返回 None
        """
        @retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_fixed(retry_delay),
            retry=retry_if_result(lambda result: result is None),
            reraise=False
        )
        def _inpaint():
            return self.inpaint_image(
                original_image, 
                mask_image,
                full_page_image=full_page_image,
                crop_box=crop_box
            )
        
        result = _inpaint()
        if result is None:
            logger.error(f"❌ {max_retries}次尝试全部失败")
        return result


