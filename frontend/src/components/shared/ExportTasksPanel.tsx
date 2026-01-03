import React, { useState } from 'react';
import { Download, X, Trash2, ChevronDown, ChevronUp, FileText, Clock, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { useExportTasksStore, type ExportTask, type ExportTaskType } from '@/store/useExportTasksStore';
import type { Page } from '@/types';
import { Button } from './Button';
import { cn } from '@/utils';

const taskTypeLabels: Record<ExportTaskType, string> = {
  'pptx': 'PPTX',
  'pdf': 'PDF',
  'editable-pptx': '可编辑 PPTX',
};

/**
 * 计算页数范围显示文本
 * @param pageIds 选中的页面ID列表，undefined表示全部
 * @param pages 所有页面列表
 * @returns 页数范围文本，如"全部"、"第1-3页"、"第2页"
 */
const getPageRangeText = (pageIds: string[] | undefined, pages: Page[]): string => {
  if (!pageIds || pageIds.length === 0) {
    return '全部';
  }
  
  if (pageIds.length === 1) {
    // 单个页面，找到索引
    const pageIndex = pages.findIndex(p => (p.id || p.page_id) === pageIds[0]);
    if (pageIndex >= 0) {
      return `第${pageIndex + 1}页`;
    }
    return '1页';
  }
  
  // 多个页面，找到最小和最大索引
  const indices: number[] = [];
  pageIds.forEach(pageId => {
    const index = pages.findIndex(p => (p.id || p.page_id) === pageId);
    if (index >= 0) {
      indices.push(index);
    }
  });
  
  if (indices.length === 0) {
    return `${pageIds.length}页`;
  }
  
  indices.sort((a, b) => a - b);
  const minIndex = indices[0];
  const maxIndex = indices[indices.length - 1];
  
  // 如果是连续的，显示范围；否则显示数量
  if (indices.length === maxIndex - minIndex + 1) {
    // 连续范围
    if (minIndex === maxIndex) {
      return `第${minIndex + 1}页`;
    }
    return `第${minIndex + 1}-${maxIndex + 1}页`;
  } else {
    // 不连续，显示数量
    return `${pageIds.length}页`;
  }
};

const TaskStatusIcon: React.FC<{ status: ExportTask['status'] }> = ({ status }) => {
  switch (status) {
    case 'PENDING':
      return <Clock size={16} className="text-gray-400" />;
    case 'PROCESSING':
    case 'RUNNING':
      return <Loader2 size={16} className="text-banana-500 animate-spin" />;
    case 'COMPLETED':
      return <CheckCircle size={16} className="text-green-500" />;
    case 'FAILED':
      return <XCircle size={16} className="text-red-500" />;
    default:
      return null;
  }
};

const TaskItem: React.FC<{ task: ExportTask; pages: Page[]; onRemove: () => void }> = ({ task, pages, onRemove }) => {
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  };

  const pageRangeText = getPageRangeText(task.pageIds, pages);

  return (
    <div className="flex items-center gap-3 py-2 px-3 hover:bg-gray-50 rounded-lg transition-colors">
      <TaskStatusIcon status={task.status} />
      
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-700 truncate">
            {taskTypeLabels[task.type]}
          </span>
          <span className="text-xs text-gray-500">
            {pageRangeText}
          </span>
          <span className="text-xs text-gray-400">
            {formatTime(task.createdAt)}
          </span>
        </div>
        
        {(task.status === 'PROCESSING' || task.status === 'RUNNING') && task.progress && (
          <div className="mt-1">
            <div className="h-1 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-banana-500 transition-all duration-300"
                style={{ width: `${task.progress.percent || 0}%` }}
              />
            </div>
            {task.progress.current_step && (
              <p className="text-xs text-gray-500 mt-0.5 truncate">
                {task.progress.current_step}
              </p>
            )}
          </div>
        )}
        
        {task.status === 'FAILED' && task.errorMessage && (
          <p className="text-xs text-red-500 mt-0.5 truncate" title={task.errorMessage}>
            {task.errorMessage}
          </p>
        )}
      </div>
      
      <div className="flex items-center gap-1 flex-shrink-0">
        {task.status === 'COMPLETED' && task.downloadUrl && (
          <Button
            variant="primary"
            size="sm"
            icon={<Download size={14} />}
            onClick={() => window.open(task.downloadUrl, '_blank')}
            className="text-xs px-2 py-1"
          >
            下载
          </Button>
        )}
        
        <button
          onClick={onRemove}
          className="p-1 text-gray-400 hover:text-gray-600 transition-colors"
          title="移除"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
};

interface ExportTasksPanelProps {
  projectId?: string;
  pages?: Page[];
  className?: string;
}

export const ExportTasksPanel: React.FC<ExportTasksPanelProps> = ({ projectId, pages = [], className }) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const { tasks, removeTask, clearCompleted } = useExportTasksStore();
  
  // Filter tasks for current project if projectId is provided
  const filteredTasks = projectId 
    ? tasks.filter(task => task.projectId === projectId)
    : tasks;
  
  const activeTasks = filteredTasks.filter(
    task => task.status === 'PENDING' || task.status === 'PROCESSING' || task.status === 'RUNNING'
  );
  const completedTasks = filteredTasks.filter(
    task => task.status === 'COMPLETED' || task.status === 'FAILED'
  );
  
  if (filteredTasks.length === 0) {
    return null;
  }
  
  return (
    <div className={cn(
      "bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden",
      className
    )}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          <FileText size={18} className="text-gray-600" />
          <span className="text-sm font-medium text-gray-700">
            导出任务
          </span>
          {activeTasks.length > 0 && (
            <span className="px-1.5 py-0.5 text-xs bg-banana-100 text-banana-700 rounded-full">
              {activeTasks.length} 进行中
            </span>
          )}
        </div>
        {isExpanded ? (
          <ChevronUp size={18} className="text-gray-500" />
        ) : (
          <ChevronDown size={18} className="text-gray-500" />
        )}
      </button>
      
      {/* Content */}
      {isExpanded && (
        <div className="max-h-64 overflow-y-auto">
          {/* Active tasks */}
          {activeTasks.length > 0 && (
            <div className="p-2 border-b border-gray-100">
              {activeTasks.map(task => (
                <TaskItem 
                  key={task.id} 
                  task={task}
                  pages={pages}
                  onRemove={() => removeTask(task.id)}
                />
              ))}
            </div>
          )}
          
          {/* Completed tasks */}
          {completedTasks.length > 0 && (
            <div className="p-2">
              <div className="flex items-center justify-between px-3 py-1 mb-1">
                <span className="text-xs text-gray-400">历史记录</span>
                <button
                  onClick={clearCompleted}
                  className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"
                >
                  <Trash2 size={12} />
                  清除
                </button>
              </div>
              {completedTasks.map(task => (
                <TaskItem 
                  key={task.id} 
                  task={task}
                  pages={pages}
                  onRemove={() => removeTask(task.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

