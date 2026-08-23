import React from 'react';

interface ConfirmDialogProps {
  isOpen: boolean;
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  onCancel: () => void;
  variant?: 'danger' | 'warning' | 'info';
}

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  title = 'Potvrďte akci',
  message,
  confirmText = 'Potvrdit',
  cancelText = 'Zrušit',
  onConfirm,
  onCancel,
  variant = 'warning'
}) => {
  if (!isOpen) return null;

  const variantStyles = {
    danger: 'bg-negative hover:bg-negative',
    warning: 'bg-warning hover:bg-warning',
    info: 'bg-accent hover:bg-accent'
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-surface-base bg-opacity-50">
      <div className="bg-surface-overlay rounded-lg shadow-xl p-6 max-w-md w-full mx-4">
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        <p className="text-text-muted mb-6 whitespace-pre-line">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-text-muted bg-surface-active rounded hover:bg-surface-active transition-colors"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className={`px-4 py-2 text-text-primary rounded transition-colors ${variantStyles[variant]}`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;


