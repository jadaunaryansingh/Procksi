import React from 'react';

export default function EmptyState({ message = "No data found.", icon: Icon }) {
  return (
    <div className="flex flex-col items-center justify-center p-8 bg-gray-50 border border-dashed border-gray-300 rounded-lg max-w-xl mx-auto my-8 text-center">
      <div className="text-gray-400 mb-4">
        {Icon ? (
          <Icon className="w-12 h-12" />
        ) : (
          <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0a2 2 0 01-2 2H6a2 2 0 01-2-2m16 0V9a2 2 0 00-2-2H6a2 2 0 00-2 2v4m16 0h-1.5m-13.5 0H6" />
          </svg>
        )}
      </div>
      <p className="text-gray-500 font-medium">{message}</p>
    </div>
  );
}
