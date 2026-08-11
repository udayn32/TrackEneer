import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import Script from 'next/script';
import './globals.css';
import { NextAuthProvider } from './components/Providers';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'TrackEneer',
  description: 'Your Personal AI Companion for Academic & Career Success',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const perfShim = `
    (function () {
      if (typeof window === 'undefined' || !window.performance) return;
      var perf = window.performance;
      if (typeof perf.clearMarks !== 'function') perf.clearMarks = function () {};
      if (typeof perf.clearMeasures !== 'function') perf.clearMeasures = function () {};
      if (typeof perf.getEntriesByName !== 'function') perf.getEntriesByName = function () { return []; };
      if (typeof perf.mark !== 'function') perf.mark = function () {};
      if (typeof perf.measure !== 'function') perf.measure = function () { return { startTime: 0, duration: 0, name: '' }; };
    })();
  `;

  return (
    <html lang="en">
      <body className={`${inter.className} bg-slate-900`}>
        <Script id="perf-shim" strategy="beforeInteractive">
          {perfShim}
        </Script>
        <NextAuthProvider>
          {children}
        </NextAuthProvider>
      </body>
  
</html>
  );
}