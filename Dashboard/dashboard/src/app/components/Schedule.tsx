const NextTask = () => {
    return(
        //card container
        <div className='bg-yellow-100 p-6 rounded-lg shadow-md w-full 
        dark:bg-gray-700 dark:text-white'>
            <h2 className="text-2xl font-bold mb-4">Next Task</h2>
            {/*Box with a task*/}
            <div className="bg-white/50 border-2 border-gray-400 rounded-lg p-4 mb-6 text center h-32 flex flex-col justify-center
            dark:bg-gray-600 dark:border-gray-500">
            <p className="text-4xl font-bold">Sleeping</p>
            <p className="text-lg text-gray-600 mt-2
            dark:text-gray-300">4 hrs</p>
        </div>
        <button className="w-full bg-gray-700 text-white py-2 rounded-lg hover:bg-gray-600
        dark:bg-blue-500 dark:hover:bg-blue-600">
            Go to Schedule
        </button>
        </div>
    );
};

export default NextTask;