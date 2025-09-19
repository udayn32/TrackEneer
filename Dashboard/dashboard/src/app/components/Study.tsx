const RecentFiles = () => {
    return (
        
            <div className='bg-orange-100 p-6 rounded-lg shadow-md w-full dark:bg-gray-700 dark:text-white'>
                <h2 className="text-2xl font-bold mb-4">Recent Files</h2>
            <div className="bg-white/50 border-2 border-gray-400 rounded-lg p-4 mb-6 dark:bg-gray-600 dark:border-gray-500">
            <ul className='list-disc list-inside space-y-2'>
                <li className='bg-white/10 p-2 rounded-lg'>DSA Notes</li>
                <li className='bg-white/10 p-2 rounded-lg'>Lecture 1 - CN</li>
                <li className='bg-white/10 p-2 rounded-lg'>Data mining QB</li>
            </ul>
            </div>
            <button className="w-full bg-gray-700 text-white py-2 rounded-lg
             hover:bg-gray-600 dark:bg-blue-500 dark:hover:bg-blue-600">
                Go to Study
            </button>
        </div>
    );
};

export default RecentFiles;
