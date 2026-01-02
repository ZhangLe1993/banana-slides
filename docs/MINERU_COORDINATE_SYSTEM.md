# MinerU 坐标系统说明文档

## 概述

MinerU API 返回的结果包含多个 JSON 文件，其中包含不同坐标系统的 bbox（边界框）信息。本文档详细说明各文件中坐标系统的含义和转换方法。

## 文件结构

MinerU 解析结果目录通常包含以下文件：

```
mineru_files/{extract_id}/
├── {uuid}_content_list.json   # 内容列表（❌ 坐标系统不可靠）
├── {uuid}_model.json           # 模型数据（归一化坐标 0-1）
├── layout.json                 # 布局数据（✅ 推荐使用）
├── full.md                     # Markdown 输出
├── {uuid}_origin.pdf           # 原始 PDF
└── images/                     # 提取的图片（低分辨率）
```

## 坐标系统对比

### 1. layout.json（推荐使用）✅

**坐标系**: PDF 点坐标系（72 DPI）

**示例**:
```json
{
  "pdf_info": [{
    "page_size": [720, 405],    // PDF 页面尺寸（点）
    "para_blocks": [{
      "type": "image",
      "bbox": [12, 8, 707, 138]  // PDF 坐标系中的像素位置
    }]
  }]
}
```

**特点**:
- 坐标单位是 PDF 点（points，72 DPI）
- 坐标系原点在左上角
- 对于 16:9 的 PDF（10英寸 × 5.625英寸），page_size 为 [720, 405]
- bbox 格式: `[x0, y0, x1, y1]`，其中 (x0, y0) 是左上角，(x1, y1) 是右下角

**转换到原始图片坐标**:
```python
original_image_width = 960    # 原始图片宽度
original_image_height = 540   # 原始图片高度
pdf_width = 720               # PDF 页面宽度
pdf_height = 405              # PDF 页面高度

scale_x = original_image_width / pdf_width    # 1.3333
scale_y = original_image_height / pdf_height  # 1.3333

# 转换 bbox
original_bbox = [
    bbox[0] * scale_x,  # x0
    bbox[1] * scale_y,  # y0
    bbox[2] * scale_x,  # x1
    bbox[3] * scale_y   # y1
]
```

**验证**:
```
layout.json bbox: [12, 8, 707, 138]
映射到原图 (960x540): [16, 10, 942, 184]
✅ 正确：这是顶部横幅图片的位置
```

### 2. content_list.json（不推荐）❌

**坐标系**: 未知/不一致的坐标系

**示例**:
```json
[{
  "type": "image",
  "bbox": [16, 19, 981, 340],  // 坐标系未知
  "page_idx": 0
}]
```

**问题**:
- 坐标范围约 981×908，超出原图 960×540 和 PDF 720×405
- X 和 Y 方向的缩放比例不一致（X: ~1.33, Y: ~2.37）
- 无法可靠地映射回原始图片
- **不建议使用此文件的 bbox 坐标**

**验证**:
```
content_list.json bbox: [16, 19, 981, 340]
X 缩放: 981 / 707 = 1.39
Y 缩放: 340 / 138 = 2.46
❌ 错误：X 和 Y 缩放比例不一致，无法正确映射
```

### 3. model.json（归一化坐标）

**坐标系**: 归一化坐标（0-1 范围）

**示例**:
```json
[{
  "type": "image",
  "bbox": [0.017, 0.022, 0.983, 0.341]  // 归一化坐标
}]
```

**特点**:
- bbox 值在 0-1 之间
- 相对于 PDF 页面的比例坐标
- 可用于不同分辨率的转换

**转换到原始图片坐标**:
```python
original_bbox = [
    bbox[0] * original_image_width,
    bbox[1] * original_image_height,
    bbox[2] * original_image_width,
    bbox[3] * original_image_height
]
```

## 实际案例分析

### 测试图片信息
- **原始图片尺寸**: 960 × 540 像素
- **PDF 尺寸**: 720 × 405 点（10" × 5.625"，72 DPI）
- **目标 PPTX**: 1920 × 1080 像素

### 第一个图片元素（顶部横幅）

| 文件 | bbox 坐标 | 映射到原图 (960×540) | 结果 |
|------|-----------|---------------------|------|
| layout.json | `[12, 8, 707, 138]` | `[16, 10, 942, 184]` | ✅ 正确 |
| content_list.json | `[16, 19, 981, 340]` | 无法正确映射 | ❌ 错误 |
| model.json | `[0.017, 0.022, 0.983, 0.341]` | `[16, 11, 943, 184]` | ✅ 可用 |

## 完整工作流程

### 方案 A: 使用 layout.json（推荐）

```python
import json
from PIL import Image

# 1. 读取原始图片尺寸
original_img = Image.open('original.png')
img_width, img_height = original_img.size  # 960, 540

# 2. 读取 layout.json
with open('layout.json') as f:
    layout_data = json.load(f)

# 3. 获取 PDF 页面尺寸
pdf_info = layout_data['pdf_info'][0]
pdf_width, pdf_height = pdf_info['page_size']  # 720, 405

# 4. 计算缩放比例
scale_x = img_width / pdf_width    # 1.3333
scale_y = img_height / pdf_height  # 1.3333

# 5. 处理每个元素
for block in pdf_info['para_blocks']:
    if block['type'] == 'image':
        bbox = block['bbox']  # [x0, y0, x1, y1]
        
        # 6. 转换到原图坐标
        original_bbox = [
            bbox[0] * scale_x,
            bbox[1] * scale_y,
            bbox[2] * scale_x,
            bbox[3] * scale_y
        ]
        
        # 7. 从原图裁剪高清区域
        cropped = original_img.crop(original_bbox)
        
        # 8. 添加到 PPTX
        # ...
```

### 方案 B: 使用 model.json

```python
# model.json 使用归一化坐标，可以直接乘以原图尺寸
for item in model_data:
    if item['type'] == 'image':
        normalized_bbox = item['bbox']  # [0.017, 0.022, 0.983, 0.341]
        
        original_bbox = [
            normalized_bbox[0] * img_width,
            normalized_bbox[1] * img_height,
            normalized_bbox[2] * img_width,
            normalized_bbox[3] * img_height
        ]
        
        cropped = original_img.crop(original_bbox)
```

## 建议

1. **✅ 优先使用 layout.json**: 坐标最准确，缩放比例统一
2. **✅ 备选 model.json**: 归一化坐标，适合多分辨率场景
3. **❌ 避免使用 content_list.json 的 bbox**: 坐标系统不可靠

## 常见错误

### 错误 1: 直接使用 content_list.json bbox
```python
# ❌ 错误
bbox = content_list_item['bbox']  # [16, 19, 981, 340]
cropped = original_img.crop(bbox)  # 位置完全错误！
```

### 错误 2: 混淆目标 PPTX 尺寸和原图尺寸
```python
# ❌ 错误：使用 PPTX 尺寸计算缩放
scale_x = pptx_width / pdf_width  # 1920 / 720 = 2.67
# 这会导致从原图裁剪时坐标超出范围

# ✅ 正确：使用原图尺寸计算缩放
scale_x = original_img_width / pdf_width  # 960 / 720 = 1.33
```

### 错误 3: 不检查坐标边界
```python
# ❌ 错误：不检查边界
cropped = original_img.crop(bbox)  # 可能超出图片范围

# ✅ 正确：裁剪前检查边界
x0 = max(0, min(bbox[0], img_width))
y0 = max(0, min(bbox[1], img_height))
x1 = max(0, min(bbox[2], img_width))
y1 = max(0, min(bbox[3], img_height))
cropped = original_img.crop((x0, y0, x1, y1))
```

## 总结

- **MinerU 有多个输出文件，坐标系统各不相同**
- **layout.json 最可靠**：使用 PDF 点坐标，可准确映射到原图
- **content_list.json 不可靠**：坐标系统未知，X/Y 缩放不一致
- **关键是使用正确的缩放比例**：`原图尺寸 / PDF尺寸`，而不是 `PPTX尺寸 / PDF尺寸`

