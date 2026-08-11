'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/**
 * Lightweight redirect from legacy /placement route to unified /career
 * 
 * This page exists only for backward compatibility. All placement functionality
 * has been unified into the Career Center at /career?tab=company
 */
export default function PlacementPage() {
  const router = useRouter();

  useEffect(() => {
    // Redirect to Career Center company tab
    router.replace('/career?tab=company');
  }, [router]);

  // Show loading state while redirecting
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-cyan-400 mx-auto mb-4" />
        <p className="text-slate-300 text-lg font-medium">Redirecting to Career Center...</p>
        <p className="text-slate-500 text-sm mt-2">Placement research has moved to /career</p>
      </div>
    </div>
  );
}
