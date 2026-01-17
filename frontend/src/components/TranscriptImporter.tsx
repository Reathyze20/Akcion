/**
 * TranscriptImporter Component
 * 
 * Allows importing transcripts with historical dates.
 * Supports both manual paste and potentially file upload.
 */

import React, { useState } from 'react';
import { apiClient } from '../api/client';
import type { TranscriptImportResponse } from '../types';

interface TranscriptImporterProps {
  onImportSuccess?: (response: TranscriptImportResponse) => void;
  onClose?: () => void;
}

const TranscriptImporter: React.FC<TranscriptImporterProps> = ({ 
  onImportSuccess,
  onClose 
}) => {
  const [formData, setFormData] = useState({
    source_name: 'Mark Gomes',
    video_date: new Date().toISOString().split('T')[0],
    raw_text: '',
    video_url: '',
    transcript_quality: 'medium' as 'high' | 'medium' | 'low'
  });
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<TranscriptImportResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (formData.raw_text.length < 100) {
      setError('Transcript must be at least 100 characters');
      return;
    }
    
    try {
      setLoading(true);
      setError(null);
      
      const response = await apiClient.importTranscript(formData);
      setSuccess(response);
      onImportSuccess?.(response);
      
      // Reset form
      setFormData(prev => ({
        ...prev,
        raw_text: '',
        video_url: ''
      }));
      
    } catch (err: any) {
      setError(err.detail || err.message || 'Failed to import transcript');
      console.error('Import error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-gray-700 bg-gray-800/50 flex items-center justify-between">
        <h3 className="text-lg font-bold text-white flex items-center gap-2">
          📝 Import Transcript
        </h3>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            ✕
          </button>
        )}
      </div>
      
      {/* Form */}
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        {/* Source & Date Row */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Source
            </label>
            <select
              value={formData.source_name}
              onChange={e => setFormData(prev => ({ ...prev, source_name: e.target.value }))}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="Mark Gomes">Mark Gomes</option>
              <option value="Breakout Investors">Breakout Investors</option>
              <option value="Other">Other</option>
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Video Date
            </label>
            <input
              type="date"
              value={formData.video_date}
              onChange={e => setFormData(prev => ({ ...prev, video_date: e.target.value }))}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              required
            />
          </div>
        </div>
        
        {/* Video URL */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Video URL (optional)
          </label>
          <input
            type="url"
            value={formData.video_url}
            onChange={e => setFormData(prev => ({ ...prev, video_url: e.target.value }))}
            placeholder="https://youtube.com/watch?v=..."
            className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        
        {/* Quality */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Transcript Quality
          </label>
          <div className="flex gap-4">
            {(['high', 'medium', 'low'] as const).map(quality => (
              <label key={quality} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="quality"
                  checked={formData.transcript_quality === quality}
                  onChange={() => setFormData(prev => ({ ...prev, transcript_quality: quality }))}
                  className="text-blue-500 focus:ring-blue-500"
                />
                <span className={`text-sm capitalize ${
                  quality === 'high' ? 'text-green-400' :
                  quality === 'medium' ? 'text-yellow-400' :
                  'text-red-400'
                }`}>
                  {quality}
                </span>
              </label>
            ))}
          </div>
        </div>
        
        {/* Transcript Text */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            Transcript Text
          </label>
          <textarea
            value={formData.raw_text}
            onChange={e => setFormData(prev => ({ ...prev, raw_text: e.target.value }))}
            placeholder="Paste the full transcript here..."
            rows={10}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
            required
            minLength={100}
          />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>{formData.raw_text.length} characters</span>
            <span className={formData.raw_text.length >= 100 ? 'text-green-500' : 'text-red-400'}>
              Min: 100 characters
            </span>
          </div>
        </div>
        
        {/* Error */}
        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
            ⚠️ {error}
          </div>
        )}
        
        {/* Success */}
        {success && (
          <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-lg text-green-400 text-sm">
            <div className="font-medium mb-1">✅ {success.message}</div>
            <div className="text-xs">
              Detected tickers: {success.detected_tickers.join(', ') || 'None'}
            </div>
          </div>
        )}
        
        {/* Submit */}
        <button
          type="submit"
          disabled={loading || formData.raw_text.length < 100}
          className={`w-full py-3 rounded-lg font-medium transition-colors ${
            loading || formData.raw_text.length < 100
              ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
              : 'bg-blue-600 hover:bg-blue-700 text-white'
          }`}
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
              Importing...
            </span>
          ) : (
            '📥 Import Transcript'
          )}
        </button>
      </form>
      
      {/* Tips */}
      <div className="p-4 bg-gray-800/30 border-t border-gray-700">
        <h4 className="text-sm font-medium text-gray-300 mb-2">💡 Tips</h4>
        <ul className="text-xs text-gray-400 space-y-1">
          <li>• Use historical dates to build a timeline of recommendations</li>
          <li>• Tickers are automatically detected from the text</li>
          <li>• Higher quality transcripts provide better AI analysis</li>
          <li>• You can process transcripts with AI later for sentiment extraction</li>
        </ul>
      </div>
    </div>
  );
};

export default TranscriptImporter;
