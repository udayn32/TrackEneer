'use client';

import { SessionProvider } from 'next-auth/react';
import { GlobalKnowledgeCapture } from './GlobalKnowledgeCapture';

type Props = {
  children?: React.ReactNode;
};

export const NextAuthProvider = ({ children }: Props) => {
  return (
    <SessionProvider>
      <GlobalKnowledgeCapture />
      {children}
    </SessionProvider>
  );
};