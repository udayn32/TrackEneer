"use client";

import Header from "./components/Header";
import NextTask from "./components/Schedule";
import RecentFiles from "./components/Study";

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-100 dark:bg-slate-950 p-8">
      <Header />
      <div className="mt-8 flex gap-8 flex-col md:flex-row">
        <NextTask />
        <RecentFiles />
      </div>
    </main>
  );
}
