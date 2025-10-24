'use client';

import { useState } from 'react';
import { signIn } from 'next-auth/react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') || 'http://localhost:5000';

export default function RegisterPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const router = useRouter();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    try {
      const res = await fetch(`${API_BASE}/api/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password }),
      });

      if (res.ok) {
        const signInRes = await signIn('credentials', {
          redirect: false,
          email,
          password,
        });
        if (signInRes?.ok) {
          router.push('/dashboard');
        } else if (signInRes?.error) {
          setError(signInRes.error);
        }
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data?.detail || data?.message || 'Registration failed.');
      }
    } catch (err) {
      setError('Unable to reach the server. Please try again.');
    }
  };

  const handleOAuth = async (provider) => {
    setError('');
    await signIn(provider, { callbackUrl: '/dashboard' });
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md p-8 space-y-6 bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-2xl shadow-2xl"
      >
        <div className="text-center">
          <h1 className="text-3xl font-bold text-cyan-400">Create Your Account</h1>
          <p className="mt-2 text-slate-400">Join TrackEneer to get started</p>
        </div>

        {error && <p className="text-center text-red-400 bg-red-500/10 p-2 rounded-md">{error}</p>}

        <div className="space-y-3">
          <button
            type="button"
            onClick={() => handleOAuth('google')}
            className="w-full flex items-center justify-center gap-2 font-semibold py-3 px-4 bg-white text-slate-900 rounded-lg border border-slate-200 hover:bg-slate-100 transition-colors"
          >
            <span role="img" aria-label="Google">🔍</span>
            Continue with Google
          </button>
          <button
            type="button"
            onClick={() => handleOAuth('github')}
            className="w-full flex items-center justify-center gap-2 font-semibold py-3 px-4 bg-slate-900 text-slate-100 rounded-lg border border-slate-600 hover:bg-slate-800 transition-colors"
          >
            <span role="img" aria-label="GitHub">🐙</span>
            Continue with GitHub
          </button>
        </div>

        <div className="relative py-2 text-center">
          <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-slate-700" aria-hidden="true" />
          <span className="relative bg-slate-800/50 px-3 text-xs uppercase tracking-widest text-slate-400">or create with email</span>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm font-medium text-slate-300">Full Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full mt-1 p-3 bg-slate-900 rounded-md border border-slate-700 focus:outline-none focus:ring-2 focus:ring-cyan-500"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-300">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full mt-1 p-3 bg-slate-900 rounded-md border border-slate-700 focus:outline-none focus:ring-2 focus:ring-cyan-500"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-300">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full mt-1 p-3 bg-slate-900 rounded-md border border-slate-700 focus:outline-none focus:ring-2 focus:ring-cyan-500"
            />
          </div>
          <button type="submit" className="w-full font-bold py-3 px-4 bg-cyan-500 hover:bg-cyan-400 text-slate-900 rounded-lg transition-colors">
            Create Account
          </button>
        </form>

        <p className="text-center text-sm text-slate-400">
          Already have an account?{' '}
          <Link href="/login" className="font-medium text-cyan-400 hover:underline">
            Sign In
          </Link>
        </p>
      </motion.div>
    </div>
  );
}