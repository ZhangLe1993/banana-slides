"""
Export Controller - handles file export endpoints
"""
from flask import Blueprint, request, current_app
from models import db, Project, Page, Task
from utils import error_response, not_found, bad_request, success_response
from services import ExportService, FileService
import os
import io

export_bp = Blueprint('export', __name__, url_prefix='/api/projects')


@export_bp.route('/<project_id>/export/pptx', methods=['GET'])
def export_pptx(project_id):
    """
    GET /api/projects/{project_id}/export/pptx?filename=... - Export PPTX
    
    Returns:
        JSON with download URL, e.g.
        {
            "success": true,
            "data": {
                "download_url": "/files/{project_id}/exports/xxx.pptx",
                "download_url_absolute": "http://host:port/files/{project_id}/exports/xxx.pptx"
            }
        }
    """
    try:
        project = Project.query.get(project_id)
        
        if not project:
            return not_found('Project')
        
        # Get all completed pages
        pages = Page.query.filter_by(project_id=project_id).order_by(Page.order_index).all()
        
        if not pages:
            return bad_request("No pages found for project")
        
        # Get image paths
        file_service = FileService(current_app.config['UPLOAD_FOLDER'])
        
        image_paths = []
        for page in pages:
            if page.generated_image_path:
                abs_path = file_service.get_absolute_path(page.generated_image_path)
                image_paths.append(abs_path)
        
        if not image_paths:
            return bad_request("No generated images found for project")
        
        # Determine export directory and filename
        file_service = FileService(current_app.config['UPLOAD_FOLDER'])
        exports_dir = file_service._get_exports_dir(project_id)
        
        # Get filename from query params or use default
        filename = request.args.get('filename', f'presentation_{project_id}.pptx')
        if not filename.endswith('.pptx'):
            filename += '.pptx'

        output_path = os.path.join(exports_dir, filename)

        # Generate PPTX file on disk
        ExportService.create_pptx_from_images(image_paths, output_file=output_path)

        # Build download URLs
        download_path = f"/files/{project_id}/exports/{filename}"
        base_url = request.url_root.rstrip("/")
        download_url_absolute = f"{base_url}{download_path}"

        return success_response(
            data={
                "download_url": download_path,
                "download_url_absolute": download_url_absolute,
            },
            message="Export PPTX task created"
        )
    
    except Exception as e:
        return error_response('SERVER_ERROR', str(e), 500)


@export_bp.route('/<project_id>/export/pdf', methods=['GET'])
def export_pdf(project_id):
    """
    GET /api/projects/{project_id}/export/pdf?filename=... - Export PDF
    
    Returns:
        JSON with download URL, e.g.
        {
            "success": true,
            "data": {
                "download_url": "/files/{project_id}/exports/xxx.pdf",
                "download_url_absolute": "http://host:port/files/{project_id}/exports/xxx.pdf"
            }
        }
    """
    try:
        project = Project.query.get(project_id)
        
        if not project:
            return not_found('Project')
        
        # Get all completed pages
        pages = Page.query.filter_by(project_id=project_id).order_by(Page.order_index).all()
        
        if not pages:
            return bad_request("No pages found for project")
        
        # Get image paths
        file_service = FileService(current_app.config['UPLOAD_FOLDER'])
        
        image_paths = []
        for page in pages:
            if page.generated_image_path:
                abs_path = file_service.get_absolute_path(page.generated_image_path)
                image_paths.append(abs_path)
        
        if not image_paths:
            return bad_request("No generated images found for project")
        
        # Determine export directory and filename
        file_service = FileService(current_app.config['UPLOAD_FOLDER'])
        exports_dir = file_service._get_exports_dir(project_id)

        # Get filename from query params or use default
        filename = request.args.get('filename', f'presentation_{project_id}.pdf')
        if not filename.endswith('.pdf'):
            filename += '.pdf'

        output_path = os.path.join(exports_dir, filename)

        # Generate PDF file on disk
        ExportService.create_pdf_from_images(image_paths, output_file=output_path)

        # Build download URLs
        download_path = f"/files/{project_id}/exports/{filename}"
        base_url = request.url_root.rstrip("/")
        download_url_absolute = f"{base_url}{download_path}"

        return success_response(
            data={
                "download_url": download_path,
                "download_url_absolute": download_url_absolute,
            },
            message="Export PDF task created"
        )
    
    except Exception as e:
        return error_response('SERVER_ERROR', str(e), 500)


@export_bp.route('/<project_id>/export/editable-pptx', methods=['POST'])
def export_editable_pptx(project_id):
    """
    POST /api/projects/{project_id}/export/editable-pptx - Export Editable PPTX (Async)
    
    This endpoint creates an async task that:
    1. Generates clean background images (removes text, icons) in parallel
    2. Converts images to PDF
    3. Sends PDF to MinerU for parsing
    4. Creates editable PPTX from MinerU results + clean backgrounds
    
    Request body (JSON):
        {
            "filename": "optional_custom_name.pptx"
        }
    
    Returns:
        JSON with task_id, e.g.
        {
            "success": true,
            "data": {
                "task_id": "uuid-here"
            },
            "message": "Export task created"
        }
    
    Poll /api/projects/{project_id}/tasks/{task_id} for progress and download URL
    """
    try:
        import uuid
        import logging
        
        logger = logging.getLogger(__name__)
        
        project = Project.query.get(project_id)
        
        if not project:
            return not_found('Project')
        
        # Get all completed pages
        pages = Page.query.filter_by(project_id=project_id).order_by(Page.order_index).all()
        
        if not pages:
            return bad_request("No pages found for project")
        
        # Check if pages have generated images
        has_images = any(page.generated_image_path for page in pages)
        if not has_images:
            return bad_request("No generated images found for project")
        
        # Get filename from request body
        data = request.get_json() or {}
        filename = data.get('filename', f'presentation_editable_{project_id}.pptx')
        if not filename.endswith('.pptx'):
            filename += '.pptx'
        
        # Create task record
        task = Task(
            project_id=project_id,
            task_type='EXPORT_EDITABLE_PPTX',
            status='PENDING'
        )
        db.session.add(task)
        db.session.commit()
        
        logger.info(f"Created export task {task.id} for project {project_id}")
        
        # Get services
        from services.ai_service import AIService
        from services.file_service import FileService
        from services.task_manager import task_manager, export_editable_pptx_task
        
        ai_service = AIService()
        file_service = FileService(current_app.config['UPLOAD_FOLDER'])
        
        # Get configuration
        aspect_ratio = current_app.config.get('DEFAULT_ASPECT_RATIO', '16:9')
        resolution = current_app.config.get('DEFAULT_RESOLUTION', '2K')
        max_workers = current_app.config.get('MAX_IMAGE_WORKERS', 8)
        
        # Get Flask app instance for background task
        app = current_app._get_current_object()
        
        # Submit background task
        task_manager.submit_task(
            task.id,
            export_editable_pptx_task,
            project_id=project_id,
            filename=filename,
            ai_service=ai_service,
            file_service=file_service,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            max_workers=max_workers,
            app=app
        )
        
        logger.info(f"Submitted export task {task.id} to task manager")
        
        return success_response(
            data={
                "task_id": task.id
            },
            message="Export task created"
        )
    
    except Exception as e:
        logger.exception("Error creating export task")
        return error_response('SERVER_ERROR', str(e), 500)

