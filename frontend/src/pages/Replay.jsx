import React, { useState, useEffect } from 'react';

function Replay() {
  const [reports, setReports] = useState([
    {
      id: 1,
      date: '2026-04-23',
      title: '2026-04-23 复盘报告',
      summary: '市场继续走强，人工智能板块领涨，成交量明显放大。',
      status: '已完成',
    },
    {
      id: 2,
      date: '2026-04-22',
      title: '2026-04-22 复盘报告',
      summary: '指数突破3900点，半导体板块表现强势。',
      status: '已完成',
    },
    {
      id: 3,
      date: '2026-04-21',
      title: '2026-04-21 复盘报告',
      summary: '市场震荡整理，新能源板块回调。',
      status: '已完成',
    },
  ]);
  const [selectedReport, setSelectedReport] = useState(null);

  // 模拟报告详情
  const reportDetails = {
    marketOverview: {
      index: '3950.25',
      change: '+1.25%',
      volume: '1.5万亿',
      upStocks: 2300,
      downStocks: 1200,
      limitUp: 150,
      limitDown: 20,
    },
    mainTrend: '人工智能、半导体、新能源',
    coreStocks: [
      { name: '寒武纪', code: '688256', price: '256.78', change: '+5.23%' },
      { name: '宁德时代', code: '300750', price: '234.56', change: '+3.45%' },
      { name: '比亚迪', code: '002594', price: '278.90', change: '+2.12%' },
    ],
    strategy: '关注龙头股低吸机会，控制仓位',
    portfolio: '持有寒武纪、宁德时代、比亚迪',
  };

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-800">复盘报告</h2>
        <button className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-600">
          生成今日复盘
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* 报告列表 */}
        <div className="md:col-span-1">
          <div className="bg-white p-4 rounded-lg shadow">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">历史报告</h3>
            <div className="space-y-2">
              {reports.map((report) => (
                <div
                  key={report.id}
                  className={`p-3 rounded-md cursor-pointer ${selectedReport?.id === report.id ? 'bg-blue-50 border-l-4 border-primary' : 'hover:bg-gray-50'}`}
                  onClick={() => setSelectedReport(report)}
                >
                  <h4 className="font-medium text-gray-800">{report.title}</h4>
                  <p className="text-sm text-gray-500">{report.summary}</p>
                  <div className="mt-2 flex items-center justify-between">
                    <span className="text-xs text-gray-400">{report.date}</span>
                    <span className={`text-xs px-2 py-1 rounded-full ${report.status === '已完成' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>
                      {report.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 报告详情 */}
        <div className="md:col-span-2">
          <div className="bg-white p-6 rounded-lg shadow">
            {selectedReport ? (
              <div className="space-y-6">
                <div>
                  <h3 className="text-xl font-bold text-gray-800">{selectedReport.title}</h3>
                  <p className="text-gray-500">{selectedReport.date}</p>
                </div>

                {/* 市场概览 */}
                <div className="border-t pt-4">
                  <h4 className="text-lg font-semibold text-gray-800 mb-3">市场概览</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-3 bg-gray-50 rounded-md">
                      <div className="text-sm text-gray-500">上证指数</div>
                      <div className="text-xl font-bold text-gray-800">{reportDetails.marketOverview.index}</div>
                      <div className="text-green-500">{reportDetails.marketOverview.change}</div>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-md">
                      <div className="text-sm text-gray-500">成交量</div>
                      <div className="text-xl font-bold text-gray-800">{reportDetails.marketOverview.volume}</div>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-md">
                      <div className="text-sm text-gray-500">涨跌家数</div>
                      <div className="text-xl font-bold text-gray-800">{reportDetails.marketOverview.upStocks}:{reportDetails.marketOverview.downStocks}</div>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-md">
                      <div className="text-sm text-gray-500">涨跌停</div>
                      <div className="text-xl font-bold text-gray-800">{reportDetails.marketOverview.limitUp}:{reportDetails.marketOverview.limitDown}</div>
                    </div>
                  </div>
                </div>

                {/* 主线分析 */}
                <div className="border-t pt-4">
                  <h4 className="text-lg font-semibold text-gray-800 mb-3">主线分析</h4>
                  <p className="text-gray-700">{reportDetails.mainTrend}</p>
                </div>

                {/* 核心标的 */}
                <div className="border-t pt-4">
                  <h4 className="text-lg font-semibold text-gray-800 mb-3">核心标的</h4>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">股票名称</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">代码</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">价格</th>
                          <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">涨跌幅</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {reportDetails.coreStocks.map((stock, index) => (
                          <tr key={index}>
                            <td className="px-6 py-4 whitespace-nowrap">{stock.name}</td>
                            <td className="px-6 py-4 whitespace-nowrap">{stock.code}</td>
                            <td className="px-6 py-4 whitespace-nowrap">{stock.price}</td>
                            <td className="px-6 py-4 whitespace-nowrap text-green-500">{stock.change}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* 交易策略 */}
                <div className="border-t pt-4">
                  <h4 className="text-lg font-semibold text-gray-800 mb-3">交易策略</h4>
                  <p className="text-gray-700">{reportDetails.strategy}</p>
                </div>

                {/* 持仓建议 */}
                <div className="border-t pt-4">
                  <h4 className="text-lg font-semibold text-gray-800 mb-3">持仓建议</h4>
                  <p className="text-gray-700">{reportDetails.portfolio}</p>
                </div>

                <div className="border-t pt-4 flex justify-end">
                  <button className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-600 mr-2">
                    导出报告
                  </button>
                  <button className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50">
                    分享报告
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center h-64">
                <p className="text-gray-500">请选择一份复盘报告查看详情</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Replay;
