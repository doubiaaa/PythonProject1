import React, { useState, useEffect } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

// 模拟数据
const marketData = [
  { date: '2026-04-19', close: 3800, volume: 1200 },
  { date: '2026-04-20', close: 3850, volume: 1300 },
  { date: '2026-04-21', close: 3820, volume: 1100 },
  { date: '2026-04-22', close: 3900, volume: 1400 },
  { date: '2026-04-23', close: 3950, volume: 1500 },
];

const sentimentData = [
  { name: '看涨', value: 60 },
  { name: '看跌', value: 25 },
  { name: '中性', value: 15 },
];

const strategyData = [
  { name: '打板', value: 30 },
  { name: '低吸', value: 25 },
  { name: '趋势', value: 20 },
  { name: '龙头', value: 20 },
  { name: '其他', value: 5 },
];

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

function Dashboard() {
  const [currentDate, setCurrentDate] = useState(new Date().toISOString().split('T')[0]);
  const [marketOverview, setMarketOverview] = useState({
    index: '3950.25',
    change: '+1.25%',
    volume: '1.5万亿',
    upStocks: 2300,
    downStocks: 1200,
    limitUp: 150,
    limitDown: 20,
  });

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-800">市场概览</h2>
        <div className="flex items-center space-x-4">
          <input 
            type="date" 
            value={currentDate} 
            onChange={(e) => setCurrentDate(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-md"
          />
          <button className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-600">
            刷新数据
          </button>
        </div>
      </div>

      {/* 市场核心指标 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="text-sm text-gray-500">上证指数</div>
          <div className="text-2xl font-bold text-gray-800">{marketOverview.index}</div>
          <div className="text-green-500">{marketOverview.change}</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="text-sm text-gray-500">成交量</div>
          <div className="text-2xl font-bold text-gray-800">{marketOverview.volume}</div>
          <div className="text-sm text-gray-500">较昨日 +12%</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="text-sm text-gray-500">涨跌家数</div>
          <div className="text-2xl font-bold text-gray-800">{marketOverview.upStocks}:{marketOverview.downStocks}</div>
          <div className="text-green-500">涨多跌少</div>
        </div>
        <div className="bg-white p-4 rounded-lg shadow">
          <div className="text-sm text-gray-500">涨跌停</div>
          <div className="text-2xl font-bold text-gray-800">{marketOverview.limitUp}:{marketOverview.limitDown}</div>
          <div className="text-green-500">涨停潮</div>
        </div>
      </div>

      {/* 图表区域 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 指数走势 */}
        <div className="bg-white p-4 rounded-lg shadow">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">指数走势</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={marketData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="close" stroke="#0088FE" strokeWidth={2} />
              <Line type="monotone" dataKey="volume" stroke="#00C49F" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* 市场情绪 */}
        <div className="bg-white p-4 rounded-lg shadow">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">市场情绪</h3>
          <div className="flex items-center justify-center">
            <ResponsiveContainer width="80%" height={300}>
              <PieChart>
                <Pie
                  data={sentimentData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  outerRadius={100}
                  fill="#8884d8"
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {sentimentData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 策略权重 */}
        <div className="bg-white p-4 rounded-lg shadow">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">策略权重</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={strategyData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="value" fill="#8884d8">
                {strategyData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* 最新复盘摘要 */}
        <div className="bg-white p-4 rounded-lg shadow">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">最新复盘摘要</h3>
          <div className="space-y-4">
            <div className="border-l-4 border-primary pl-4 py-2">
              <h4 className="font-medium text-gray-800">市场主线</h4>
              <p className="text-gray-600">人工智能、半导体、新能源</p>
            </div>
            <div className="border-l-4 border-secondary pl-4 py-2">
              <h4 className="font-medium text-gray-800">核心标的</h4>
              <p className="text-gray-600">寒武纪、宁德时代、比亚迪</p>
            </div>
            <div className="border-l-4 border-accent pl-4 py-2">
              <h4 className="font-medium text-gray-800">明日策略</h4>
              <p className="text-gray-600">关注龙头股低吸机会，控制仓位</p>
            </div>
          </div>
          <div className="mt-4">
            <a href="/replay" className="text-primary hover:underline">查看完整复盘报告</a>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
