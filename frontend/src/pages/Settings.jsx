import React, { useState, useEffect } from 'react';

function Settings() {
  const [activeTab, setActiveTab] = useState('llm');
  const [settings, setSettings] = useState({
    llm: {
      apiKey: '',
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
      smtpHost: '',
      smtpPort: 587,
      smtpUser: '',
      smtpPassword: '',
      mailTo: '',
      enableEmail: false,
    },
    system: {
      enableReplayCheckpoint: true,
      enableStyleStabilityProbe: false,
      enableWeeklyReport: true,
    },
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  // 从后端 API 获取配置
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        setLoading(true);
        const token = localStorage.getItem('token');
        if (!token) {
          setError('请先登录');
          setLoading(false);
          return;
        }

        const response = await fetch('http://localhost:8000/api/config/', {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          throw new Error('获取配置失败');
        }

        const configData = await response.json();
        
        // 解析配置数据
        setSettings(prev => ({
          ...prev,
          llm: {
            ...prev.llm,
            apiKey: configData.deepseek_api_key?.value || '',
          },
          email: {
            ...prev.email,
            smtpHost: configData.smtp_host?.value || '',
            smtpPort: parseInt(configData.smtp_port?.value || '587'),
            smtpUser: configData.smtp_user?.value || '',
            smtpPassword: configData.smtp_password?.value || '',
            mailTo: configData.mail_to?.value || '',
            enableEmail: configData.enable_email?.value === 'true',
          },
        }));
        
        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchConfig();
  }, []);

  const handleSettingChange = (section, key, value) => {
    setSettings(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: key === 'smtpPort' || key === 'cacheExpire' || key === 'retryTimes' || key === 'temperature' || key === 'maxTokens' ? parseFloat(value) : value
      }
    }));
  };

  const saveSettings = async () => {
    try {
      setSaving(true);
      setMessage(null);
      const token = localStorage.getItem('token');
      if (!token) {
        setError('请先登录');
        setSaving(false);
        return;
      }

      // 保存 LLM 配置
      await fetch('http://localhost:8000/api/config/deepseek_api_key', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: settings.llm.apiKey }),
      });

      // 保存邮件配置
      await fetch('http://localhost:8000/api/config/smtp_host', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: settings.email.smtpHost }),
      });

      await fetch('http://localhost:8000/api/config/smtp_port', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: settings.email.smtpPort.toString() }),
      });

      await fetch('http://localhost:8000/api/config/smtp_user', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: settings.email.smtpUser }),
      });

      await fetch('http://localhost:8000/api/config/smtp_password', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: settings.email.smtpPassword }),
      });

      await fetch('http://localhost:8000/api/config/mail_to', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: settings.email.mailTo }),
      });

      await fetch('http://localhost:8000/api/config/enable_email', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: settings.email.enableEmail.toString() }),
      });

      setMessage('设置已保存');
      setError(null);
    } catch (err) {
      setError('保存设置失败');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="flex items-center justify-center h-64">加载中...</div>;
  }

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-800">系统设置</h2>
        <button 
          className="px-4 py-2 bg-primary text-white rounded-md hover:bg-blue-600" 
          onClick={saveSettings}
          disabled={saving}
        >
          {saving ? '保存中...' : '保存设置'}
        </button>
      </div>

      {/* 消息提示 */}
      {message && (
        <div className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded">
          {message}
        </div>
      )}

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* 设置选项卡 */}
      <div className="bg-white p-6 rounded-lg shadow">
        <div className="flex border-b">
          <button 
            className={`px-4 py-2 ${activeTab === 'llm' ? 'border-b-2 border-primary text-primary font-medium' : 'text-gray-500 hover:text-gray-700'}`}
            onClick={() => setActiveTab('llm')}
          >
            LLM 设置
          </button>
          <button 
            className={`px-4 py-2 ${activeTab === 'email' ? 'border-b-2 border-primary text-primary font-medium' : 'text-gray-500 hover:text-gray-700'}`}
            onClick={() => setActiveTab('email')}
          >
            邮件设置
          </button>
        </div>

        {/* LLM 设置 */}
        {activeTab === 'llm' && (
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
        )}

        {/* 邮件设置 */}
        {activeTab === 'email' && (
          <div className="mt-6 space-y-4">
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
        )}
      </div>
    </div>
  );
}

export default Settings;
