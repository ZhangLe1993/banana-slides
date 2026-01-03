"""
测试混合提取器 - MinerU版面分析 + 百度高精度OCR
"""
import sys
import os
from pathlib import Path

# 添加backend到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from dotenv import load_dotenv
# 加载项目根目录的.env文件
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from PIL import Image, ImageDraw, ImageFont
import random

# 类型颜色映射
TYPE_COLORS = {
    'image': (255, 100, 100),      # 红色 - 图片
    'figure': (255, 100, 100),
    'chart': (255, 100, 100),
    'diagram': (255, 100, 100),
    'table': (100, 255, 100),      # 绿色 - 表格
    'table_cell': (150, 255, 150),
    'text': (100, 100, 255),       # 蓝色 - 文字
    'title': (150, 100, 255),      # 紫色 - 标题
    'paragraph': (100, 150, 255),
    'header': (200, 200, 100),     # 黄色 - 页眉页脚
    'footer': (200, 200, 100),
}


def get_color_for_type(elem_type: str, source: str = None):
    """根据元素类型获取颜色"""
    base_color = TYPE_COLORS.get(elem_type, (128, 128, 128))
    
    # 如果来源是百度OCR，颜色更亮一些
    if source == 'baidu_ocr':
        return tuple(min(255, c + 50) for c in base_color)
    
    return base_color


def draw_elements_on_image(image_path: str, elements: list, output_path: str):
    """
    在图片上绘制识别的元素bbox
    
    Args:
        image_path: 原图路径
        elements: 元素列表
        output_path: 输出图片路径
    """
    # 打开图片
    img = Image.open(image_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    draw = ImageDraw.Draw(img)
    
    # 尝试加载字体
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 12)
        except:
            font = ImageFont.load_default()
    
    print(f"\n📝 识别到 {len(elements)} 个元素:")
    print("-" * 70)
    
    # 统计各类型数量
    type_counts = {}
    source_counts = {'mineru': 0, 'baidu_ocr': 0}
    
    for idx, elem in enumerate(elements):
        elem_type = elem.get('type', 'unknown')
        content = elem.get('content', '')
        bbox = elem.get('bbox', [0, 0, 0, 0])
        metadata = elem.get('metadata', {})
        source = metadata.get('source', 'unknown')
        in_table = metadata.get('in_table', False)
        
        # 统计
        type_counts[elem_type] = type_counts.get(elem_type, 0) + 1
        if source in source_counts:
            source_counts[source] += 1
        
        # 获取颜色
        color = get_color_for_type(elem_type, source)
        
        # 绘制bbox
        x0, y0, x1, y1 = bbox
        draw.rectangle([x0, y0, x1, y1], outline=color, width=2)
        
        # 绘制标签
        source_tag = "🔤" if source == 'baidu_ocr' else "📄"
        table_tag = "📊" if in_table else ""
        label = f"{idx+1}{source_tag}{table_tag}"
        
        # 计算文字背景
        text_bbox = draw.textbbox((x0, y0 - 16), label, font=font)
        draw.rectangle(text_bbox, fill=color)
        draw.text((x0, y0 - 16), label, fill='white', font=font)
        
        # 打印识别结果
        content_preview = content[:30] + '...' if content and len(content) > 30 else (content or '(无内容)')
        print(f"[{idx+1}] 类型: {elem_type:<12} 来源: {source:<10} bbox: [{x0:.0f}, {y0:.0f}, {x1:.0f}, {y1:.0f}]")
        print(f"     内容: {content_preview}")
        if in_table:
            print(f"     📊 在表格区域内")
        print()
    
    # 保存结果
    img.save(output_path)
    
    print("-" * 70)
    print("📊 统计信息:")
    print(f"   来源: MinerU={source_counts['mineru']}, 百度OCR={source_counts['baidu_ocr']}")
    print(f"   类型: {type_counts}")
    print("-" * 70)
    print(f"✅ 结果已保存到: {output_path}")
    
    # 绘制图例
    draw_legend(img, output_path)
    
    return img


def draw_legend(img, output_path):
    """绘制图例"""
    legend_height = 120
    legend_width = 300
    
    # 创建带图例的新图片
    new_img = Image.new('RGB', (img.width, img.height + legend_height), (255, 255, 255))
    new_img.paste(img, (0, 0))
    
    draw = ImageDraw.Draw(new_img)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 12)
        except:
            font = ImageFont.load_default()
    
    y_offset = img.height + 10
    draw.text((10, y_offset), "图例:", fill='black', font=font)
    
    legend_items = [
        ('image/figure', (255, 100, 100), '图片'),
        ('table', (100, 255, 100), '表格'),
        ('text', (100, 100, 255), '文字(MinerU)'),
        ('text(OCR)', (150, 150, 255), '文字(百度OCR)'),
        ('title', (150, 100, 255), '标题'),
    ]
    
    x_offset = 60
    for name, color, label in legend_items:
        draw.rectangle([x_offset, y_offset + 25, x_offset + 20, y_offset + 40], fill=color, outline='black')
        draw.text((x_offset + 25, y_offset + 25), label, fill='black', font=font)
        x_offset += 100
    
    # 来源说明
    y_offset += 55
    draw.text((10, y_offset), "来源标记: 📄=MinerU  🔤=百度OCR  📊=在表格区域内", fill='black', font=font)
    
    new_img.save(output_path)


def main():
    # 测试图片路径 (WSL格式)
    image_path = "/mnt/d/Desktop/带表格图片.png"
    output_path = "/mnt/d/Desktop/带表格图片_hybrid_result.png"
    
    print("=" * 70)
    print("混合提取器测试 (MinerU + 百度高精度OCR)")
    print("=" * 70)
    print(f"📸 输入图片: {image_path}")
    
    # 检查图片是否存在
    if not os.path.exists(image_path):
        print(f"❌ 图片不存在: {image_path}")
        return
    
    # 获取配置
    from flask import Flask
    app = Flask(__name__)
    
    # 从环境变量获取配置
    mineru_token = os.getenv('MINERU_TOKEN')
    mineru_api_base = os.getenv('MINERU_API_BASE', 'https://mineru.net')
    upload_folder = Path(__file__).parent / 'uploads'
    
    if not mineru_token:
        print("❌ 未配置 MINERU_TOKEN 环境变量")
        return
    
    print(f"✅ MinerU Token: {mineru_token[:20]}...")
    print(f"✅ MinerU API: {mineru_api_base}")
    
    # 创建MinerU解析服务
    from services.file_parser_service import FileParserService
    parser_service = FileParserService(
        mineru_token=mineru_token,
        mineru_api_base=mineru_api_base
    )
    print("✅ MinerU解析服务创建成功")
    
    # 创建混合提取器
    from services.image_editability import ExtractorFactory
    
    hybrid_extractor = ExtractorFactory.create_hybrid_extractor(
        parser_service=parser_service,
        upload_folder=upload_folder,
        contain_threshold=0.8,
        intersection_threshold=0.3
    )
    
    if hybrid_extractor is None:
        print("❌ 无法创建混合提取器，请检查配置")
        return
    
    print("✅ 混合提取器创建成功")
    
    # 开始提取
    print("\n🔍 开始混合提取...")
    print("-" * 70)
    
    try:
        result = hybrid_extractor.extract(image_path)
        elements = result.elements
        
        print(f"\n✅ 提取完成，共 {len(elements)} 个元素")
        
        # 绘制结果
        draw_elements_on_image(image_path, elements, output_path)
        
    except Exception as e:
        print(f"❌ 提取失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
