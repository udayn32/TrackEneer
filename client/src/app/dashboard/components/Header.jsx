"use client";

import { useTheme } from "next-themes";
import { FaCog, FaUserCircle, FaSun, FaMoon } from 'react-icons/fa';

const Header = () => {
  const { theme, setTheme } = useTheme();

  return (
    <header className="bg-blue-500 text-white p-4 rounded-lg flex flex-col md:flex-row items-center justify-between gap-4 dark:bg-gray-800">
      
      {/* Left side: Welcome and Theme Toggle */}
      <div className="flex items-center gap-6">
        <h1 className="text-3xl font-bold">Welcome, User</h1>
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="flex items-center gap-2 bg-white/20 hover:bg-white/30 p-2 rounded-lg transition-all"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <FaSun size={20} /> : <FaMoon size={20} />}
        </button>
      </div>

      {/* Middle: Quote */}
      <div className="text-center">
        <p className="text-xl md:text-2xl italic font-serif">
          Push harder than yesterday, if you want a different tomorrow
        </p>
      </div>

      {/* Right side: Avatar and Logout */}
      <div className="flex items-center gap-4">
        <FaUserCircle size={40} />
        <button className="bg-white text-blue-500 font-bold py-2 px-4 rounded-lg hover:bg-gray-200 transition-colors dark:text-gray-800">
          Logout
        </button>
      </div>

    </header>
  );
};

export default Header;
