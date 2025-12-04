import React, { useState, useRef, useEffect } from 'react';
import { MessageCircle, X, ChevronRight, Send, Loader2 } from 'lucide-react';
import { Button, useToast } from '@/components/shared';
import { agentChat } from '@/api/endpoints';
import { useParams } from 'react-router-dom';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface AgentWindowProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AgentWindow: React.FC<AgentWindowProps> = ({ isOpen, onClose }) => {
  const { projectId } = useParams<{ projectId: string }>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { show } = useToast();
  const [isEntering, setIsEntering] = useState(false);

  // 滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      // 进入时启动缓冲动画
      setIsEntering(false);
      // 下一帧再切换到进入状态，触发过渡
      const timer = requestAnimationFrame(() => {
        setIsEntering(true);
        scrollToBottom();
      });
      return () => cancelAnimationFrame(timer);
    } else {
      setIsEntering(false);
    }
  }, [messages, isOpen]);

  const handleSend = async () => {
    if (!input.trim() || !projectId || isLoading) return;

    const userMessage: Message = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await agentChat(projectId, userMessage.content);
      
      if (response.success && response.data) {
        const assistantMessage: Message = {
          role: 'assistant',
          content: response.data.response || '收到',
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, assistantMessage]);
      } else {
        show({
          message: response.error?.message || 'Agent响应失败',
          type: 'error',
        });
      }
    } catch (error: any) {
      console.error('Agent chat error:', error);
      show({
        message: error?.response?.data?.error?.message || error.message || '发送失败',
        type: 'error',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className={`h-full w-full bg-white shadow-lg flex flex-col border-l border-gray-200 transform transition-transform transition-opacity duration-200 ease-out ${
        isEntering ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-gradient-to-r from-banana-500 to-banana-600 text-white">
        <div className="flex items-center gap-2">
          <MessageCircle size={20} />
          <h3 className="font-semibold">AI 助手</h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 hover:bg-white/20 rounded transition-colors"
          aria-label="关闭"
        >
          <X size={18} />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
        {messages.length === 0 ? (
          <div className="text-center text-gray-500 mt-8">
            <MessageCircle size={48} className="mx-auto mb-4 opacity-50" />
            <p className="text-sm">开始与AI助手对话</p>
            <p className="text-xs mt-2 text-gray-400">
              可以要求编辑图片、更新描述、修改大纲等
            </p>
          </div>
        ) : (
          messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-lg p-3 ${
                  message.role === 'user'
                    ? 'bg-banana-500 text-white'
                    : 'bg-white text-gray-800 border border-gray-200'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap break-words">
                  {message.content}
                </p>
                <p
                  className={`text-xs mt-1 ${
                    message.role === 'user' ? 'text-banana-100' : 'text-gray-400'
                  }`}
                >
                  {message.timestamp.toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white rounded-lg p-3 border border-gray-200">
              <Loader2 size={16} className="animate-spin text-banana-500" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-200 bg-white">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="输入消息... (Enter发送, Shift+Enter换行)"
            className="flex-1 min-h-[60px] max-h-[120px] px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-banana-500 resize-none text-sm"
            disabled={isLoading}
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            variant="primary"
            className="self-end"
          >
            {isLoading ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Send size={18} />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};

