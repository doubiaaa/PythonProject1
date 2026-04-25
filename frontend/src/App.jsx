import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Replay from './pages/Replay';
import Strategy from './pages/Strategy';
import Backtest from './pages/Backtest';
import Settings from './pages/Settings';
import Login from './pages/Login';

// 私有路由组件
function PrivateRoute({ children }) {
  const token = localStorage.getItem('token');
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [user, setUser] = useState(null);

  useEffect(() => {
    const userStr = localStorage.getItem('user');
    if (userStr) {
      setUser(JSON.parse(userStr));
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    setUser(null);
  };

  return (
    <Router>
      <Routes>
        {/* 登录页面 */}
        <Route path="/login" element={<Login />} />
        
        {/* 主应用 */}
        <Route path="/*" element={
          <div className="flex h-screen bg-gray-100">
            {/* 侧边栏 */}
            <div className={`${isSidebarOpen ? 'w-64' : 'w-16'} bg-white shadow-md transition-all duration-300 ease-in-out`}>
              <div className="p-4 border-b">
                <h1 className={`text-xl font-bold text-primary ${!isSidebarOpen && 'hidden'}`}>
                  智能复盘系统
                </h1>
                <div className="text-primary font-bold text-2xl ${isSidebarOpen && 'hidden'}">
                  智
                </div>
              </div>
              <nav className="mt-4">
                <ul>
                  <li>
                    <Link to="/" className="flex items-center px-4 py-3 text-gray-700 hover:bg-blue-50">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                      </svg>
                      <span className={!isSidebarOpen && 'hidden'}>仪表盘</span>
                    </Link>
                  </li>
                  <li>
                    <Link to="/replay" className="flex items-center px-4 py-3 text-gray-700 hover:bg-blue-50">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                      <span className={!isSidebarOpen && 'hidden'}>复盘报告</span>
                    </Link>
                  </li>
                  <li>
                    <Link to="/strategy" className="flex items-center px-4 py-3 text-gray-700 hover:bg-blue-50">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                      </svg>
                      <span className={!isSidebarOpen && 'hidden'}>策略分析</span>
                    </Link>
                  </li>
                  <li>
                    <Link to="/backtest" className="flex items-center px-4 py-3 text-gray-700 hover:bg-blue-50">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                      <span className={!isSidebarOpen && 'hidden'}>回测系统</span>
                    </Link>
                  </li>
                  {user && (
                    <li>
                      <Link to="/settings" className="flex items-center px-4 py-3 text-gray-700 hover:bg-blue-50">
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        <span className={!isSidebarOpen && 'hidden'}>设置</span>
                      </Link>
                    </li>
                  )}
                </ul>
              </nav>
              <div className="absolute bottom-0 left-0 right-0 p-4 border-t">
                {user ? (
                  <button 
                    onClick={handleLogout}
                    className="flex items-center justify-center w-full p-2 rounded-md hover:bg-gray-100"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                    </svg>
                    <span className={`ml-2 ${!isSidebarOpen && 'hidden'}`}>退出登录</span>
                  </button>
                ) : (
                  <Link to="/login" className="flex items-center justify-center w-full p-2 rounded-md hover:bg-gray-100">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                    </svg>
                    <span className={`ml-2 ${!isSidebarOpen && 'hidden'}`}>登录</span>
                  </Link>
                )}
                <button 
                  onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                  className="flex items-center justify-center w-full p-2 rounded-md hover:bg-gray-100 mt-2"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className={`h-6 w-6 ${isSidebarOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                  </svg>
                  <span className={`ml-2 ${!isSidebarOpen && 'hidden'}`}>
                    {isSidebarOpen ? '收起' : '展开'}
                  </span>
                </button>
              </div>
            </div>

            {/* 主内容区域 */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* 顶部导航栏 */}
              <header className="bg-white shadow-sm">
                <div className="flex items-center justify-between px-6 py-4">
                  <div className="flex items-center">
                    <button 
                      onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                      className="mr-4"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16m-7 6h7" />
                      </svg>
                    </button>
                    <h1 className="text-xl font-bold text-gray-800">
                      A股收盘智能复盘系统
                    </h1>
                  </div>
                  <div className="flex items-center space-x-4">
                    <button className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-600">
                      执行复盘
                    </button>
                    <div className="relative">
                      <button className="flex items-center space-x-2">
                        <div className="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center">
                          <span className="text-gray-600">{user ? user.username.charAt(0) : '用'}</span>
                        </div>
                        <span className="text-gray-700">{user ? user.username : '用户'}</span>
                      </button>
                    </div>
                  </div>
                </div>
              </header>

              {/* 内容区域 */}
              <main className="flex-1 overflow-y-auto p-6">
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/replay" element={<Replay />} />
                  <Route path="/strategy" element={<Strategy />} />
                  <Route path="/backtest" element={<Backtest />} />
                  <Route 
                    path="/settings" 
                    element={
                      <PrivateRoute>
                        <Settings />
                      </PrivateRoute>
                    } 
                  />
                </Routes>
              </main>
            </div>
          </div>
        } />
      </Routes>
    </Router>
  );
}

export default App;
