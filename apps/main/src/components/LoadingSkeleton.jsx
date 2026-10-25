import React from 'react';

export default function LoadingSkeleton({ lines = 3, className = "" }) {
  return (
    <div className={`w-full animate-pulse space-y-3 ${className}`}>
      {Array.from({ length: lines }).map((_, idx) => (
        <div
          key={idx}
          className={`h-4 bg-gray-200 rounded-md dark:bg-gray-700`}
          style={{ width: idx === lines - 1 ? '60%' : '100%' }}
        />
      ))}
    </div>
  );
}
