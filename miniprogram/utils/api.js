/**
 * Wrapper around wx.request that adds auth header and base URL.
 * getApp() is called inside each function (not at top level) to avoid
 * "App not registered yet" errors during module loading.
 */
function request(method, path, data) {
  const app = getApp();
  return new Promise((resolve, reject) => {
    const token = app.globalData.token;
    const headers = { 'Content-Type': 'application/json' };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    wx.request({
      url: `${app.globalData.baseUrl}${path}`,
      method,
      data: data || null,
      header: headers,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject({ status: res.statusCode, data: res.data });
        }
      },
      fail(err) {
        reject(err);
      },
    });
  });
}

const api = {
  get: (path) => request('GET', path),
  post: (path, data) => request('POST', path, data),
  put: (path, data) => request('PUT', path, data),

  wechatLogin: (code, name, phone) =>
    request('POST', '/auth/wechat-login', { code, name, phone }),

  getCurrentSemester: () => request('GET', '/semesters/current'),

  submitRegistration: (data) => request('POST', '/registrations', data),
  getMyRegistrations: () => request('GET', '/registrations/my'),
  updateRegistration: (id, data) => request('PUT', `/registrations/${id}`, data),

  getMyPlacementRecommendations: () => request('GET', '/registrations/my/placement'),
  getMyEnrollments: () => request('GET', '/enrollments/my'),
  confirmEnrollment: (id, accepted) =>
    request('POST', `/enrollments/${id}/confirm`, { accepted }),
};

module.exports = api;
