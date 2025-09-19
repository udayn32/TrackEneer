// src/app/components/Header.tsx

"use client"; // This component now uses a hook, so it's a client component.

import { useTheme } from "next-themes";
import { FaCog, FaUserCircle, FaSun, FaMoon } from 'react-icons/fa'; // Import Sun and Moon icons

const Header = () => {
  // Use the useTheme hook
  const { theme, setTheme } = useTheme();

  return (
    // Add dark mode styles for the header
    <header className="bg-blue-500 text-white p-4 rounded-lg flex items-center justify-between dark:bg-gray-800">
      
      {/* Left side: Welcome and Settings */}
      <div className="flex items-center gap-6">
        <h1 className="text-3xl font-bold">Welcome, User</h1>
        {/* We can add a theme toggle near settings */}
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="flex items-center gap-2 bg-white/20 hover:bg-white/30 p-2 rounded-lg"
        >
          {theme === "dark" ? <FaSun size={20} /> : <FaMoon size={20} />}
        </button>
      </div>

      {/* Middle: The Quote */}
      <div>
        <p className="text-2xl italic font-serif">
          Push harder than yesterday, if you want a different tomorrow
        </p>
      </div>

      {/* Right side: Avatar and Logout */}
      <div className="flex items-center gap-4">
        <FaUserCircle size={40} />
        <button className="bg-white text-blue-500 font-bold py-2 px-4 rounded-lg hover:bg-gray-200 dark:text-gray-800">
          Logout
        </button>
      </div>

    </header>
  );
};

export default Header;