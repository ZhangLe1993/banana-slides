"""
Agent Controller - handles agent-related endpoints for slide editing
"""
import os
import logging
from flask import Blueprint, request, current_app
from models import db, Project, Page
from utils import success_response, error_response, not_found, bad_request
from agno.agent import Agent
from agno.models.google import Gemini
from agno.tools.sleep import SleepTools
from services.slide_agent_tools import SlideAgentTools

logger = logging.getLogger(__name__)

agent_bp = Blueprint('agent', __name__, url_prefix='/api/projects')


def create_slide_agent(project_id: str, app=None) -> Agent:
    """Create an Agno agent for slide editing"""
    # Get API key - agno expects GEMINI_API_KEY, but we use GOOGLE_API_KEY in this project
    # So we check both and use whichever is available
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        # Try GOOGLE_API_KEY from environment
        api_key = os.getenv("GOOGLE_API_KEY")
    
    # If still no key and we have app, try app config
    if not api_key and app:
        with app.app_context():
            api_key = current_app.config.get('GOOGLE_API_KEY', '')
    
    if not api_key:
        raise ValueError("API key not configured. Please set GEMINI_API_KEY or GOOGLE_API_KEY environment variable")
    
    model_id = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # Create tools
    slide_tools = SlideAgentTools(project_id=project_id, app=app)
    sleep_tools = SleepTools()
    
    # Get project context
    with app.app_context():
        project = Project.query.get(project_id)
        if not project:
            raise ValueError("Project not found")
        
        pages = Page.query.filter_by(project_id=project_id).order_by(Page.order_index).all()
        pages_info = []
        for i, page in enumerate(pages, 1):
            outline = page.get_outline_content() or {}
            desc = page.get_description_content() or {}
            pages_info.append({
                "index": i,
                "page_id": page.id,
                "title": outline.get('title', f'页面 {i}'),
                "has_description": bool(desc),
                "has_image": bool(page.generated_image_path),
                "status": page.status
            })
    
    instructions = f"""你是一个智能幻灯片编辑助手，可以帮助用户编辑和管理幻灯片。

## 你的能力

你拥有以下工具：
1. **edit_page_image** - 编辑页面图片（使用自然语言指令）
2. **update_page_description** - 更新页面描述内容
3. **update_page_outline** - 更新页面大纲内容
4. **regenerate_page_image** - 重新生成页面图片
5. **sleep** - 等待一段时间（当任务队列已满时使用）

## 重要规则

1. **并发任务限制**：一次最多只能执行4个异步任务（edit_page_image 和 regenerate_page_image 是异步的）
2. **任务队列管理**：如果当前有4个任务在执行，你需要使用sleep工具等待一段时间，然后再尝试
3. **异步任务**：edit_page_image 和 regenerate_page_image 会返回task_id，任务在后台执行
4. **同步任务**：update_page_description 和 update_page_outline 是同步的，会立即完成

## 当前项目信息

项目ID: {project_id}
总页数: {len(pages_info)}

页面列表:
{chr(10).join([f"  {p['index']}. {p['title']} (ID: {p['page_id']}) - 描述: {'有' if p['has_description'] else '无'}, 图片: {'有' if p['has_image'] else '无'}, 状态: {p['status']}" for p in pages_info])}

## 使用建议

- 当用户要求编辑图片时，使用 edit_page_image
- 当用户要求修改描述时，使用 update_page_description
- 当用户要求修改大纲时，使用 update_page_outline
- 当用户要求重新生成图片时，使用 regenerate_page_image
- 如果任务队列已满，使用 sleep 等待后再继续
"""
    
    agent = Agent(
        name="SlideEditor",
        model=Gemini(id=model_id, api_key=api_key),
        tools=[slide_tools, sleep_tools],
        instructions=instructions,
        markdown=True,
        debug_mode=False
    )
    
    return agent


@agent_bp.route('/<project_id>/agent/chat', methods=['POST'])
def agent_chat(project_id):
    """
    POST /api/projects/{project_id}/agent/chat - Chat with slide editing agent
    
    Request body:
    {
        "message": "请编辑第1页的图片，将背景改为蓝色"
    }
    """
    try:
        project = Project.query.get(project_id)
        if not project:
            return not_found('Project')
        
        data = request.get_json()
        if not data or 'message' not in data:
            return bad_request("message is required")
        
        message = data['message']
        
        # Get app instance for agent creation
        app_instance = current_app._get_current_object()
        
        # Create agent with app context
        agent = create_slide_agent(project_id, app=app_instance)
        
        # Get response from agent
        # Use run method which returns a RunResponse
        # Run within app context to ensure database access works
        with app_instance.app_context():
            run_response = agent.run(message)
        
        # Extract content from response
        # The response object should have a content attribute
        response_text = ""
        if hasattr(run_response, 'content'):
            response_text = run_response.content
        elif hasattr(run_response, 'messages') and run_response.messages:
            # Get last assistant message
            for msg in reversed(run_response.messages):
                if hasattr(msg, 'content'):
                    response_text = msg.content
                    break
        else:
            response_text = str(run_response)
        
        return success_response({
            "response": response_text,
            "messages": run_response.messages if hasattr(run_response, 'messages') else []
        })
    
    except Exception as e:
        logger.error(f"Agent chat error: {e}", exc_info=True)
        return error_response('AGENT_ERROR', str(e), 500)

