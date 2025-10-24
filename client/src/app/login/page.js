'use client';

import { useState } from 'react';
import { signIn } from 'next-auth/react';
import { FaGoogle, FaGithub } from 'react-icons/fa';
import { motion } from 'framer-motion';
import Link from 'next/link';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(''); // Clear previous errors

    const result = await signIn('credentials', {
      redirect: false, // Important: handle redirect manually
      email,
      password,
    });

    if (result.error) {
      setError('Invalid email or password. Please try again.');
    } else {
      // Successful login, redirect to dashboard
      window.location.href = '/dashboard';
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-white flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md p-8 space-y-6 bg-slate-800 rounded-2xl shadow-2xl"
      >
        <div className="text-center">
          <h1 className="text-3xl font-bold text-cyan-400">Welcome Back</h1>
          <p className="mt-2 text-slate-400">Sign in to your TrackEneer account</p>
        </div>

        {error && <p className="text-center text-red-400 bg-red-500/10 p-2 rounded-md">{error}</p>}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm font-medium text-slate-300">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full mt-1 p-3 bg-slate-700 rounded-md border border-slate-600 focus:outline-none focus:ring-2 focus:ring-cyan-500"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-300">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full mt-1 p-3 bg-slate-700 rounded-md border border-slate-600 focus:outline-none focus:ring-2 focus:ring-cyan-500"
            />
          </div>
          <div className="text-right text-sm">
            <Link href="/forgot-password" className="text-cyan-400 hover:underline">Forgot Password?</Link>
          </div>
          <button type="submit" className="w-full font-bold py-3 px-4 bg-cyan-500 hover:bg-cyan-600 text-slate-900 rounded-lg transition-colors">
            Sign In
          </button>
        </form>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-slate-600" />
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="bg-slate-800 px-2 text-slate-400">Or continue with</span>
          </div>
        </div>

        <div className="flex gap-4">
          <button onClick={() => signIn('google', { callbackUrl: '/oauth-register' })} className="w-full flex items-center justify-center gap-3 bg-slate-700 hover:bg-slate-600 font-semibold py-3 px-4 rounded-lg transition-colors">
            <FaGoogle /> Google
          </button>
          <button onClick={() => signIn('github', { callbackUrl: '/oauth-register' })} className="w-full flex items-center justify-center gap-3 bg-slate-700 hover:bg-slate-600 font-semibold py-3 px-4 rounded-lg transition-colors">
            <FaGithub /> GitHub
          </button>
        </div>
      </motion.div>
    </div>
  );
}