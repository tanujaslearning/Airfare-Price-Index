import React from 'react';
import { Plane, Activity } from 'lucide-react';

export const Header: React.FC = () => {
  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-sky-600 rounded-lg text-white shadow-md shadow-sky-100">
            <Plane className="w-5 h-5 transform -rotate-45" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 leading-tight">
              APIx <span className="text-sky-600">Prototype</span>
            </h1>
            <p className="text-xs text-slate-500 font-medium">Airfare Price Index System</p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-sky-50 text-sky-700 border border-sky-200">
            <Activity className="w-3.5 h-3.5 mr-1 animate-pulse" />
            Live Dashboard
          </span>
        </div>
      </div>
    </header>
  );
};
