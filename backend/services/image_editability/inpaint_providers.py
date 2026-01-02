"""
Inpaint提供者 - 抽象不同的inpaint实现

提供两种重绘方法：
1. DefaultInpaintProvider - 基于mask的精确区域重绘（使用Volcengine Inpainting服务）
2. GenerativeEditInpaintProvider - 基于生成式大模型的整图编辑重绘（如Gemini图片编辑）
"""
import logging
import tempfile
from abc import ABC, abstractmethod
from typing import List, Optional
from PIL import Image

logger = logging.getLogger(__name__)


class InpaintProvider(ABC):
    """
    Inpaint提供者抽象接口
    
    用于抽象不同的inpaint方法，支持接入多种实现：
    - 基于InpaintingService的实现（当前默认）
    - Gemini API实现
    - SD/SDXL等其他模型实现
    - 第三方API实现
    """
    
    @abstractmethod
    def inpaint_regions(
        self,
        image: Image.Image,
        bboxes: List[tuple],
        types: Optional[List[str]] = None,
        **kwargs
    ) -> Optional[Image.Image]:
        """
        对图像中指定区域进行inpaint处理
        
        Args:
            image: 原始PIL图像对象
            bboxes: 边界框列表，每个bbox格式为 (x0, y0, x1, y1)
            types: 可选的元素类型列表，与bboxes一一对应（如 'text', 'image', 'table'等）
            **kwargs: 其他由具体实现自定义的参数
        
        Returns:
            处理后的PIL图像对象，失败返回None
        """
        pass


class DefaultInpaintProvider(InpaintProvider):
    """
    基于InpaintingService的默认Inpaint提供者
    
    这是当前系统使用的实现，调用已有的InpaintingService
    """
    
    def __init__(self, inpainting_service):
        """
        初始化默认Inpaint提供者
        
        Args:
            inpainting_service: InpaintingService实例
        """
        self.inpainting_service = inpainting_service
    
    def inpaint_regions(
        self,
        image: Image.Image,
        bboxes: List[tuple],
        types: Optional[List[str]] = None,
        **kwargs
    ) -> Optional[Image.Image]:
        """
        使用InpaintingService处理inpaint
        
        支持的kwargs参数：
        - expand_pixels: int, 扩展像素数，默认10
        - merge_bboxes: bool, 是否合并bbox，默认False
        - merge_threshold: int, 合并阈值，默认20
        - save_mask_path: str, mask保存路径，可选
        - full_page_image: Image.Image, 完整页面图像（用于Gemini），可选
        - crop_box: tuple, 裁剪框 (x0, y0, x1, y1)，可选
        """
        expand_pixels = kwargs.get('expand_pixels', 10)
        merge_bboxes = kwargs.get('merge_bboxes', False)
        merge_threshold = kwargs.get('merge_threshold', 20)
        save_mask_path = kwargs.get('save_mask_path')
        full_page_image = kwargs.get('full_page_image')
        crop_box = kwargs.get('crop_box')
        
        try:
            result_img = self.inpainting_service.remove_regions_by_bboxes(
                image=image,
                bboxes=bboxes,
                expand_pixels=expand_pixels,
                merge_bboxes=merge_bboxes,
                merge_threshold=merge_threshold,
                save_mask_path=save_mask_path,
                full_page_image=full_page_image,
                crop_box=crop_box
            )
            return result_img
        except Exception as e:
            logger.error(f"DefaultInpaintProvider处理失败: {e}", exc_info=True)
            return None


class GenerativeEditInpaintProvider(InpaintProvider):
    """
    基于生成式大模型图片编辑的Inpaint提供者
    
    使用生成式大模型（如Gemini的图片编辑功能）通过自然语言指令移除图片中的文字、图标等元素。
    
    与DefaultInpaintProvider的区别：
    - DefaultInpaintProvider: 基于mask的精确区域重绘（需要准确的bbox）
    - GenerativeEditInpaintProvider: 整图生成式编辑（通过prompt描述要移除的内容）
    
    优点：不需要精确的bbox，大模型自动理解并移除相关元素
    缺点：可能改变背景细节，生成速度较慢，消耗更多token
    
    适用场景：
    - bbox不够精确时
    - 需要移除复杂或分散的元素时
    - 作为mask-based方法的备选方案
    """
    
    def __init__(self, ai_service, aspect_ratio: str = "16:9", resolution: str = "2K"):
        """
        初始化生成式编辑Inpaint提供者
        
        Args:
            ai_service: AIService实例（需要支持edit_image方法）
            aspect_ratio: 目标宽高比
            resolution: 目标分辨率
        """
        self.ai_service = ai_service
        self.aspect_ratio = aspect_ratio
        self.resolution = resolution
    
    def inpaint_regions(
        self,
        image: Image.Image,
        bboxes: List[tuple],
        types: Optional[List[str]] = None,
        **kwargs
    ) -> Optional[Image.Image]:
        """
        使用生成式大模型编辑生成干净背景
        
        注意：此方法忽略bboxes参数，通过大模型自动识别并移除所有文字和图标
        
        支持的kwargs参数：
        - aspect_ratio: str, 宽高比，默认使用初始化时的值
        - resolution: str, 分辨率，默认使用初始化时的值
        """
        aspect_ratio = kwargs.get('aspect_ratio', self.aspect_ratio)
        resolution = kwargs.get('resolution', self.resolution)
        
        try:
            from services.prompts import get_clean_background_prompt
            
            # 获取清理背景的prompt
            edit_instruction = get_clean_background_prompt()
            
            # 保存临时图片文件（AI服务需要文件路径）
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
                tmp_path = tmp_file.name
                image.save(tmp_path)
            
            logger.info("GenerativeEditInpaintProvider: 开始生成式编辑重绘...")
            
            # 调用AI服务编辑图片
            clean_bg_image = self.ai_service.edit_image(
                prompt=edit_instruction,
                current_image_path=tmp_path,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                original_description=None,
                additional_ref_images=None
            )
            
            if not clean_bg_image:
                logger.error("GenerativeEditInpaintProvider: 生成式编辑返回空结果")
                return None
            
            # 转换为PIL Image
            if not isinstance(clean_bg_image, Image.Image):
                # Google GenAI返回自己的Image类型，需要提取_pil_image
                if hasattr(clean_bg_image, '_pil_image'):
                    clean_bg_image = clean_bg_image._pil_image
                else:
                    logger.error(f"GenerativeEditInpaintProvider: 未知的图片类型: {type(clean_bg_image)}")
                    return None
            
            logger.info("GenerativeEditInpaintProvider: 重绘完成")
            return clean_bg_image
        
        except Exception as e:
            logger.error(f"GenerativeEditInpaintProvider处理失败: {e}", exc_info=True)
            return None


# 向后兼容的别名
AIEditInpaintProvider = GenerativeEditInpaintProvider

