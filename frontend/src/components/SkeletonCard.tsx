/**
 * SkeletonCard Component
 * 
 * Modern skeleton loader for stock cards during loading states.
 */

import React from 'react';

export const SkeletonCard: React.FC = () => {
  return (
    <div className="card p-5 space-y-4">
      {/* Header skeleton */}
      <div className="flex items-start justify-between">
        <div className="space-y-2 flex-1">
          <div className="skeleton h-7 w-24"></div>
          <div className="skeleton h-4 w-40"></div>
        </div>
        <div className="skeleton h-6 w-20"></div>
      </div>

      {/* Scores skeleton */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <div className="skeleton h-3 w-20"></div>
          <div className="skeleton h-8 w-16"></div>
        </div>
        <div className="space-y-2">
          <div className="skeleton h-3 w-20"></div>
          <div className="skeleton h-8 w-16"></div>
        </div>
      </div>

      {/* Content skeleton */}
      <div className="space-y-2">
        <div className="skeleton h-3 w-full"></div>
        <div className="skeleton h-3 w-5/6"></div>
        <div className="skeleton h-3 w-4/6"></div>
      </div>

      {/* Footer skeleton */}
      <div className="flex justify-between items-center pt-2">
        <div className="skeleton h-3 w-32"></div>
        <div className="skeleton h-3 w-24"></div>
      </div>
    </div>
  );
};

export const SkeletonGrid: React.FC<{ count?: number }> = ({ count = 6 }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
};


