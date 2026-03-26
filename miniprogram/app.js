App({
  globalData: {
    token: null,
    baseUrl: 'http://192.168.1.181:8000/api/v1',
  },

  onLaunch() {
    const token = wx.getStorageSync('token');
    if (token) {
      this.globalData.token = token;
    }
  },
});
