import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts';

// 模拟数据
const backtestResults = [
  { date: '2026-01', return: 2.5, benchmark: 1.2 },
  { date: '2026-02', return: 4.8, benchmark: 2.1 },
  { date: '2026-03', return: 7.2, benchmark: 3.5 },
  { date: '2026-04', return: 10.5, benchmark: 5.2 },
];

const parameterResults = [
  { param: 'alpha=0.1', return: 8.5, sharpe: 0.75 },
  { param: 'alpha=0.2', return: 9.2, sharpe: 0.81 },
  { param: 'alpha=0.3', return: 10.5, sharpe: 0.85 },
  { param: 'alpha=0.4', return: 9.8, sharpe: 0.82 },
  { param: 'alpha=0.5', return: 8.9, sharpe: 0.78 },
];

function Backtest() {
  const [parameters, setParameters] = useState({
    startDate: '2026-01-01',
    endDate: '2026-04-30',
    initialCapital: 100000,
    alpha: 0.3,
    maxWeight: 0.2,
    minWeight: 0.01,
  });
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState(null);

  const handleParameterChange = (e) => {
    const { name, value } = e.target;
    setParameters(prev => ({
      ...prev,
      [name]: name === 'initialCapital' || name === 'alpha' || name === 'maxWeight' || name === 'minWeight' ? parseFloat(value) : value
    }));
  };

  const runBacktest = () => {
    setIsRunning(true);
    // 模拟回测过程
    setTimeout(() => {
      setResults({
        totalReturn: 10.5,
        maxDrawdown: 5.2,
        sharpeRatio: 0.85,
        winRate: 65,
        trades: 45,
      });
      setIsRunning(false);
    }, 2000);
  };

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-800">回测系统</h2>
        <button 
          className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-600" 
          onClick={runBacktest}
          disabled={isRunning}
        >
          {isRunning ? '回测中...' : '运行回测'}
        </button>
      </div>

      {/* 回测参数设置 */}
      <div className="bg-white p-6 rounded-lg shadow">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">回测参数</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">开始日期</label>
              <input 
                type="date" 
                name="startDate" 
                value={parameters.startDate} 
                onChange={handleParameterChange}
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">结束日期</label>
              <input 
                type="date" 
                name="endDate" 
                value={parameters.endDate} 
                onChange={handleParameterChange}
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">初始资金</label>
              <input 
                type="number" 
                name="initialCapital" 
                value={parameters.initialCapital} 
                onChange={handleParameterChange}
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">平滑系数 (alpha)</label>
              <input 
                type="number" 
                name="alpha" 
                value={parameters.alpha} 
                onChange={handleParameterChange}
                step="0.1"
                min="0" 
                max="1"
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">单风格上限 (maxWeight)</label>
              <input 
                type="number" 
                name="maxWeight" 
                value={parameters.maxWeight} 
                onChange={handleParameterChange}
                step="0.05"
                min="0" 
                max="1"
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">单风格下限 (minWeight)</label>
              <input 
                type="number" 
                name="minWeight" 
                value={parameters.minWeight} 
                onChange={handleParameterChange}
                step="0.01"
                min="0" 
                max="1"
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
          </div>
        </div>
      </div>

      {/* 回测结果 */}
      {results && (
        <div className="space-y-6">
          {/* 核心指标 */}
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">回测结果</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">总收益率</div>
                <div className="text-xl font-bold text-green-500">{results.totalReturn.toFixed(2)}%</div>
              </div>
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">最大回撤</div>
                <div className="text-xl font-bold text-red-500">{results.maxDrawdown.toFixed(2)}%</div>
              </div>
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">夏普比率</div>
                <div className="text-xl font-bold text-gray-800">{results.sharpeRatio.toFixed(2)}</div>
              </div>
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">胜率</div>
                <div className="text-xl font-bold text-gray-800">{results.winRate.toFixed(0)}%</div>
              </div>
            </div>
          </div>

          {/* 收益曲线 */}
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">收益曲线</h3>
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={backtestResults}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="return" name="策略收益" stroke="#0088FE" strokeWidth={2} />
                <Line type="monotone" dataKey="benchmark" name="基准收益" stroke="#00C49F" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* 参数敏感性分析 */}
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">参数敏感性分析</h3>
            <ResponsiveContainer width="100%" height={400}>
              <BarChart data={parameterResults}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="param" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="return" name="收益率(%)" fill="#0088FE" />
                <Bar dataKey="sharpe" name="夏普比率" fill="#00C49F" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="flex justify-end">
            <button className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-600 mr-2">
              导出结果
            </button>
            <button className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50">
              保存配置
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default Backtest;
