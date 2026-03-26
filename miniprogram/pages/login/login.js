const { login } = require('../../utils/auth');

Page({
  data: {
    loading: false,
    error: '',
  },

  async onLoad() {
    const token = wx.getStorageSync('token');
    if (token) {
      wx.nextTick(() => this.navigateToMain());
    }
  },

  async onLogin() {
    this.setData({ loading: true, error: '' });
    try {
      await login();
      this.setData({ loading: false });
      this.navigateToMain();
    } catch (e) {
      console.error('登录失败', e);
      this.setData({ loading: false, error: '登录失败：' + (e.data?.detail || e.errMsg || JSON.stringify(e)) });
    }
  },

  navigateToMain() {
    wx.navigateTo({ url: '/pages/register/register' });
  },
});
