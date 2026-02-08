/**
 * NotificationBell Component
 * 
 * Displays a notification bell with unread count badge.
 * Dropdown shows thesis drift alerts, score changes, and reconciliation notifications.
 * 
 * Part of the "Intelligent on the inside" UX layer.
 */

import React, { useState, useEffect, useRef } from 'react';
import { Bell, AlertTriangle, TrendingDown, TrendingUp, RefreshCw } from 'lucide-react';
import { apiClient } from '../api/client';
import type { NotificationItem } from '../api/client';

interface NotificationBellProps {
  className?: string;
  onNotificationClick?: (notification: NotificationItem) => void;
}

export const NotificationBell: React.FC<NotificationBellProps> = ({
  className = '',
  onNotificationClick,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Fetch notifications on mount and periodically
  const fetchNotifications = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getNotifications(false, 20);
      setNotifications(data);
      setUnreadCount(data.filter(n => !n.is_read).length);
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
    // Refresh every 60 seconds
    const interval = setInterval(fetchNotifications, 60000);
    return () => clearInterval(interval);
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleAcknowledgeAll = async () => {
    try {
      await apiClient.acknowledgeAllAlerts();
      fetchNotifications();
    } catch (error) {
      console.error('Failed to acknowledge alerts:', error);
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'CRITICAL': return 'text-negative bg-negative/10';
      case 'WARNING': return 'text-warning bg-warning/10';
      default: return 'text-accent bg-blue-500/10';
    }
  };

  const getIcon = (type: string, severity: string) => {
    if (type === 'THESIS_DRIFT') {
      return severity === 'CRITICAL' 
        ? <AlertTriangle className="w-4 h-4" /> 
        : <TrendingDown className="w-4 h-4" />;
    }
    if (type === 'SCORE_CHANGE') {
      return <TrendingUp className="w-4 h-4" />;
    }
    return <RefreshCw className="w-4 h-4" />;
  };

  const formatTime = (timestamp: string | null) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
  };

  return (
    <div className={`relative ${className}`} ref={dropdownRef}>
      {/* Bell Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg hover:bg-surface-hover/50 transition-colors"
        aria-label="Notifications"
      >
        <Bell className={`w-5 h-5 ${unreadCount > 0 ? 'text-warning' : 'text-text-secondary'}`} />
        
        {/* Unread Badge */}
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center min-w-[18px] h-[18px] px-1 text-xs font-bold text-text-primary bg-negative rounded-full animate-pulse">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown Panel */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-96 max-h-[32rem] overflow-hidden bg-surface-raised border border-border rounded-xl shadow-2xl z-50">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <h3 className="font-semibold text-text-primary">Notifications</h3>
            <div className="flex items-center gap-2">
              <button
                onClick={fetchNotifications}
                className="p-1.5 rounded-lg hover:bg-surface-hover text-text-secondary hover:text-text-primary transition-colors"
                title="Refresh"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
              {unreadCount > 0 && (
                <button
                  onClick={handleAcknowledgeAll}
                  className="px-2 py-1 text-xs font-medium text-positive hover:bg-positive/10 rounded transition-colors"
                >
                  Mark all read
                </button>
              )}
            </div>
          </div>

          {/* Notifications List */}
          <div className="overflow-y-auto max-h-[26rem]">
            {notifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-text-muted">
                <Bell className="w-10 h-10 mb-3 opacity-30" />
                <p className="text-sm">No notifications</p>
                <p className="text-xs mt-1">You're all caught up!</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-700/50">
                {notifications.map((notification) => (
                  <button
                    key={notification.id}
                    onClick={() => onNotificationClick?.(notification)}
                    className={`w-full text-left px-4 py-3 hover:bg-surface-hover/30 transition-colors ${
                      !notification.is_read ? 'bg-surface-hover/20' : ''
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {/* Icon */}
                      <div className={`flex-shrink-0 p-2 rounded-lg ${getSeverityColor(notification.severity)}`}>
                        {getIcon(notification.type, notification.severity)}
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          {notification.ticker && (
                            <span className="px-1.5 py-0.5 text-xs font-mono font-bold bg-slate-600/50 rounded text-text-primary">
                              {notification.ticker}
                            </span>
                          )}
                          <span className={`text-xs font-medium ${getSeverityColor(notification.severity).split(' ')[0]}`}>
                            {notification.severity}
                          </span>
                        </div>
                        <p className="mt-1 text-sm font-medium text-text-primary truncate">
                          {notification.title}
                        </p>
                        <p className="mt-0.5 text-xs text-text-secondary line-clamp-2">
                          {notification.message}
                        </p>
                        {notification.timestamp && (
                          <p className="mt-1 text-xs text-text-muted">
                            {formatTime(notification.timestamp)}
                          </p>
                        )}
                      </div>

                      {/* Unread indicator */}
                      {!notification.is_read && (
                        <div className="flex-shrink-0 w-2 h-2 mt-2 bg-blue-400 rounded-full" />
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && (
            <div className="px-4 py-2 border-t border-border bg-surface-raised/50">
              <button
                onClick={() => {
                  setIsOpen(false);
                  // Could navigate to full notifications page
                }}
                className="w-full text-center text-sm text-text-secondary hover:text-text-primary transition-colors"
              >
                View all notifications
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NotificationBell;


