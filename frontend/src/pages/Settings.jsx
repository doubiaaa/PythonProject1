import React, { useState, useEffect } from 'react';

function Settings() {
  const [settings, setSettings] = useState({
    llm: {
      apiKey: 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
      model: 'deepseek-chat',
      temperature: 0.7,
      maxTokens: 2000,
    },
    dataSource: {
      cacheExpire: 3600,
      retryTimes: 3,
      parallelFetch: true,
    },
    email: {
      smtpHost: 'smtp.example.com',
      smtpPort: 587,
      smtpUser: 'user@example.com',
      smtpPassword: 'password',
      mailTo: 'recipient@example.com',
      enableEmail: false,
    },
    system: {
      enableReplayCheckpoint: true,
      enableStyleStabilityProbe: false,
      enableWeeklyReport: true,
    },
  });

  const handleSettingChange = (section, key, value) => {
    setSettings(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: key === 'smtpPort' || key === 'cacheExpire' || key === 'retryTimes' || key === 'temperature' || key === 'maxTokens' ? parseFloat(value) : value
      }
    }));
  };

  const saveSettings = () => {
    // 模拟保存设置
    alert('设置已保存');
  };

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-800">系统设置</h2>
        <button className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-600" onClick={saveSettings}>
          保存设置
        </button>
      </div>

      {/* 设置选项卡 */}
      <div className="bg-white p-6 rounded-lg shadow">
        <div className="flex border-b">
          <button className="px-4 py-2 border-b-2 border-primary text-primary font-medium">LLM 设置</button>
          <button className="px-4 py-2 text-gray-500 hover:text-gray-700">数据源设置</button>
          <button className="px-4 py-2 text-gray-500 hover:text-gray-700">邮件设置</button>
          <button className="px-4 py-2 text-gray-500 hover:text-gray-700">系统设置</button>
        </div>

        {/* LLM 设置 */}
        <div className="mt-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
            <input 
              type="password" 
              value={settings.llm.apiKey} 
              onChange={(e) => handleSettingChange('llm', 'apiKey', e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-md"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">模型</label>
            <select 
              value={settings.llm.model} 
              onChange={(e) => handleSettingChange('llm', 'model', e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-md"
            >
              <option value="deepseek-chat">DeepSeek Chat</option>
              <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
              <option value="gpt-4">GPT-4</option>
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">温度 (Temperature)</label>
              <input 
                type="number" 
                value={settings.llm.temperature} 
                onChange={(e) => handleSettingChange('llm', 'temperature', e.target.value)}
                step="0.1"
                min="0" 
                max="1"
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">最大令牌数 (Max Tokens)</label>
              <input 
                type="number" 
                value={settings.llm.maxTokens} 
                onChange={(e) => handleSettingChange('llm', 'maxTokens', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
          </div>
        </div>

        {/* 数据源设置 */}
        <div className="mt-6 space-y-4 hidden">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">缓存过期时间 (秒)</label>
              <input 
                type="number" 
                value={settings.dataSource.cacheExpire} 
                onChange={(e) => handleSettingChange('dataSource', 'cacheExpire', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">重试次数</label>
              <input 
                type="number" 
                value={settings.dataSource.retryTimes} 
                onChange={(e) => handleSettingChange('dataSource', 'retryTimes', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
          </div>
          <div className="flex items-center">
            <input 
              type="checkbox" 
              id="parallelFetch" 
              checked={settings.dataSource.parallelFetch} 
              onChange={(e) => handleSettingChange('dataSource', 'parallelFetch', e.target.checked)}
              className="mr-2"
            />
            <label htmlFor="parallelFetch" className="text-sm font-medium text-gray-700">启用并行获取</label>
          </div>
        </div>

        {/* 邮件设置 */}
        <div className="mt-6 space-y-4 hidden">
          <div className="flex items-center mb-4">
            <input 
              type="checkbox" 
              id="enableEmail" 
              checked={settings.email.enableEmail} 
              onChange={(e) => handleSettingChange('email', 'enableEmail', e.target.checked)}
              className="mr-2"
            />
            <label htmlFor="enableEmail" className="text-sm font-medium text-gray-700">启用邮件通知</label>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">SMTP 主机</label>
              <input 
                type="text" 
                value={settings.email.smtpHost} 
                onChange={(e) => handleSettingChange('email', 'smtpHost', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">SMTP 端口</label>
              <input 
                type="number" 
                value={settings.email.smtpPort} 
                onChange={(e) => handleSettingChange('email', 'smtpPort', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">SMTP 用户</label>
              <input 
                type="text" 
                value={settings.email.smtpUser} 
                onChange={(e) => handleSettingChange('email', 'smtpUser', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">SMTP 密码</label>
              <input 
                type="password" 
                value={settings.email.smtpPassword} 
                onChange={(e) => handleSettingChange('email', 'smtpPassword', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">收件人邮箱</label>
              <input 
                type="email" 
                value={settings.email.mailTo} 
                onChange={(e) => handleSettingChange('email', 'mailTo', e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-md"
              />
            </div>
          </div>
        </div>

        {/* 系统设置 */}
        <div className="mt-6 space-y-4 hidden">
          <div className="flex items-center mb-4">
            <input 
              type="checkbox" 
              id="enableReplayCheckpoint" 
              checked={settings.system.enableReplayCheckpoint} 
              onChange={(e) => handleSettingChange('system', 'enableReplayCheckpoint', e.target.checked)}
              className="mr-2"
            />
            <label htmlFor="enableReplayCheckpoint" className="text-sm font-medium text-gray-700">启用复盘断点续跑</label>
          </div>
          <div className="flex items-center mb-4">
            <input 
              type="checkbox" 
              id="enableStyleStabilityProbe" 
              checked={settings.system.enableStyleStabilityProbe} 
              onChange={(e) => handleSettingChange('system', 'enableStyleStabilityProbe', e.target.checked)}
              className="mr-2"
            />
            <label htmlFor="enableStyleStabilityProbe" className="text-sm font-medium text-gray-700">启用风格稳定性探测</label>
          </div>
          <div className="flex items-center mb-4">
            <input 
              type="checkbox" 
              id="enableWeeklyReport" 
              checked={settings.system.enableWeeklyReport} 
              onChange={(e) => handleSettingChange('system', 'enableWeeklyReport', e.target.checked)}
              className="mr-2"
            />
            <label htmlFor="enableWeeklyReport" className="text-sm font-medium text-gray-700">启用周报</label>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Settings;
