const api = require('./api');

const isDev = true; // 上线前改为 false

/**
 * Login: dev mode uses fake openid, production uses wx.login.
 * getApp() called inside (not at top level) to avoid load-order issues.
 */
function login() {
  const app = getApp();
  return new Promise((resolve, reject) => {
    if (isDev) {
      api
        .post('/auth/dev-login', {
          fake_openid: 'dev_user_001',
          name: '测试用户',
          phone: '13800000000',
        })
        .then((data) => {
          app.globalData.token = data.access_token;
          wx.setStorageSync('token', data.access_token);
          resolve(data);
        })
        .catch(reject);
      return;
    }

    wx.login({
      success(res) {
        if (!res.code) return reject(new Error('wx.login failed'));
        api
          .wechatLogin(res.code)
          .then((data) => {
            app.globalData.token = data.access_token;
            wx.setStorageSync('token', data.access_token);
            resolve(data);
          })
          .catch(reject);
      },
      fail: reject,
    });
  });
}

function getToken() {
  return getApp().globalData.token || wx.getStorageSync('token');
}

function logout() {
  getApp().globalData.token = null;
  wx.removeStorageSync('token');
}

module.exports = { login, getToken, logout };
