import React from 'react';
import { useToast, type Toast as ToastType } from '../context/ToastContext';

const Toast: React.FC<{ toast: ToastType }> = ({ toast }) => {
  const { removeToast } = useToast();

  const getIcon = () => {
    switch (toast.type) {
      case 'success':
        return '✓';
      case 'error':
        return '✕';
      case 'warning':
        return '⚠';
      case 'info':
      default:
        return 'ℹ';
    }
  };

  const getColorClasses = () => {
    switch (toast.type) {
      case 'success':
        return 'bg-green-600 border-positive';
      case 'error':
        return 'bg-red-600 border-negative';
      case 'warning':
        return 'bg-yellow-600 border-yellow-500';
      case 'info':
      default:
        return 'bg-blue-600 border-blue-500';
    }
  };

  return (
    <div
      className={`${getColorClasses()} border-l-4 p-4 mb-3 rounded-lg shadow-lg backdrop-blur-sm bg-opacity-95 
        transform transition-all duration-300 ease-in-out
        animate-slide-in-right hover:scale-105`}
      role="alert"
    >
      <div className="flex items-start">
        <div className="flex-shrink-0">
          <span className="text-text-primary text-xl font-bold">{getIcon()}</span>
        </div>
        <div className="ml-3 flex-1">
          <p className="text-sm text-text-primary whitespace-pre-line">{toast.message}</p>
        </div>
        <button
          onClick={() => removeToast(toast.id)}
          className="ml-4 text-text-primary hover:text-gray-200 transition-colors"
          aria-label="Close"
        >
          <span className="text-xl">×</span>
        </button>
      </div>
    </div>
  );
};

export const ToastContainer: React.FC = () => {
  const { toasts } = useToast();

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end space-y-2 max-w-md w-full pointer-events-none">
      <div className="pointer-events-auto w-full">
        {toasts.map(toast => (
          <Toast key={toast.id} toast={toast} />
        ))}
      </div>
    </div>
  );
};


