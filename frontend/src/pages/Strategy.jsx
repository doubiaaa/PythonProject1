import React, { useState, useEffect } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

// 模拟数据
const strategyPerformance = [
  { name: '打板', return: 12.5, volatility: 15.2, sharpe: 0.82 },
  { name: '低吸', return: 8.3, volatility: 10.5, sharpe: 0.79 },
  { name: '趋势', return: 10.2, volatility: 12.8, sharpe: 0.79 },
  { name: '龙头', return: 15.6, volatility: 18.3, sharpe: 0.85 },
  { name: '其他', return: 6.7, volatility: 9.2, sharpe: 0.73 },
];

const weightEvolution = [
  { date: '2026-01', 打板: 25, 低吸: 20, 趋势: 20, 龙头: 30, 其他: 5 },
  { date: '2026-02', 打板: 28, 低吸: 22, 趋势: 18, 龙头: 27, 其他: 5 },
  { date: '2026-03', 打板: 30, 低吸: 25, 趋势: 15, 龙头: 25, 其他: 5 },
  { date: '2026-04', 打板: 30, 低吸: 25, 趋势: 20, 龙头: 20, 其他: 5 },
];

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

function Strategy() {
  const [selectedStrategy, setSelectedStrategy] = useState('龙头');
  const [strategyDetails, setStrategyDetails] = useState({
    name: '龙头',
    description: '专注于市场龙头股的交易策略，通过识别和跟随市场最强势的个股获取超额收益。',
    parameters: {
      entryThreshold: 0.03,
      exitThreshold: -0.02,
      stopLoss: -0.05,
      takeProfit: 0.15,
    },
    performance: {
      totalReturn: 15.6,
      maxDrawdown: 8.2,
      sharpeRatio: 0.85,
      winRate: 65,
    },
  });

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-800">策略分析</h2>
        <button className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-600">
          优化策略
        </button>
      </div>

      {/* 策略概览 */}
      <div className="bg-white p-6 rounded-lg shadow">
        <h3 className="text-lg font-semibold text-gray-800 mb-4">策略表现概览</h3>
        <ResponsiveContainer width="100%" height={400}>
          <BarChart data={strategyPerformance}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="return" name="收益率(%)" fill="#0088FE" />
            <Bar dataKey="volatility" name="波动率(%)" fill="#00C49F" />
            <Bar dataKey="sharpe" name="夏普比率" fill="#FFBB28" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 策略权重演进 */}
        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">策略权重演进</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={weightEvolution}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="打板" stroke="#0088FE" strokeWidth={2} />
              <Line type="monotone" dataKey="低吸" stroke="#00C49F" strokeWidth={2} />
              <Line type="monotone" dataKey="趋势" stroke="#FFBB28" strokeWidth={2} />
              <Line type="monotone" dataKey="龙头" stroke="#FF8042" strokeWidth={2} />
              <Line type="monotone" dataKey="其他" stroke="#8884d8" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* 策略分布 */}
        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">当前策略分布</h3>
          <div className="flex items-center justify-center">
            <ResponsiveContainer width="80%" height={300}>
              <PieChart>
                <Pie
                  data={[
                    { name: '打板', value: 30 },
                    { name: '低吸', value: 25 },
                    { name: '趋势', value: 20 },
                    { name: '龙头', value: 20 },
                    { name: '其他', value: 5 },
                  ]}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  outerRadius={100}
                  fill="#8884d8"
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {strategyPerformance.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* 策略详情 */}
      <div className="bg-white p-6 rounded-lg shadow">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800">策略详情</h3>
          <div className="flex space-x-2">
            {['打板', '低吸', '趋势', '龙头', '其他'].map((strategy) => (
              <button
                key={strategy}
                className={`px-3 py-1 rounded-md ${selectedStrategy === strategy ? 'bg-primary text-white' : 'bg-gray-100 text-gray-700'}`}
                onClick={() => setSelectedStrategy(strategy)}
              >
                {strategy}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <h4 className="font-medium text-gray-800">策略描述</h4>
            <p className="text-gray-600">{strategyDetails.description}</p>
          </div>

          <div>
            <h4 className="font-medium text-gray-800">策略参数</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">入场阈值</div>
                <div className="text-lg font-bold text-gray-800">{strategyDetails.parameters.entryThreshold.toFixed(2)}</div>
              </div>
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">出场阈值</div>
                <div className="text-lg font-bold text-gray-800">{strategyDetails.parameters.exitThreshold.toFixed(2)}</div>
              </div>
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">止损</div>
                <div className="text-lg font-bold text-gray-800">{strategyDetails.parameters.stopLoss.toFixed(2)}</div>
              </div>
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">止盈</div>
                <div className="text-lg font-bold text-gray-800">{strategyDetails.parameters.takeProfit.toFixed(2)}</div>
              </div>
            </div>
          </div>

          <div>
            <h4 className="font-medium text-gray-800">策略表现</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">总收益率</div>
                <div className="text-lg font-bold text-green-500">{strategyDetails.performance.totalReturn.toFixed(2)}%</div>
              </div>
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">最大回撤</div>
                <div className="text-lg font-bold text-red-500">{strategyDetails.performance.maxDrawdown.toFixed(2)}%</div>
              </div>
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">夏普比率</div>
                <div className="text-lg font-bold text-gray-800">{strategyDetails.performance.sharpeRatio.toFixed(2)}</div>
              </div>
              <div className="p-3 bg-gray-50 rounded-md">
                <div className="text-sm text-gray-500">胜率</div>
                <div className="text-lg font-bold text-gray-800">{strategyDetails.performance.winRate.toFixed(0)}%</div>
              </div>
            </div>
          </div>

          <div className="pt-4">
            <button className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-600">
              调整参数
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Strategy;
