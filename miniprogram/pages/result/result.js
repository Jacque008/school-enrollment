const api = require('../../utils/api');

const LEVEL_MATERIALS = {
  1: '行知中文1', 2: '行知中文2', 3: '行知中文3',
  4: '华文2', 5: '华文3', 6: '华文4', 7: '华文5',
  8: '华文6', 9: '华文7', 10: '华文8', 11: '华文9',
  12: '华文10', 13: '华文11', 14: '华文12',
  15: '华文初一', 16: '华文初二', 17: '华文初三',
  18: '华文初四', 19: '华文初五',
};

function levelToMaterial(lv) {
  lv = parseInt(lv) || 0;
  if (lv <= 0) return '待定';
  if (lv <= 19) return LEVEL_MATERIALS[lv] || `L${lv}`;
  return '高级课程';
}

function levelToBand(lv) {
  lv = parseInt(lv) || 0;
  if (lv <= 5) return '小班';
  if (lv <= 12) return '中班';
  return '高班';
}

Page({
  data: {
    loading: true,
    level: null,
    material: '',
    band: '',
    enrollments: [],
  },

  async onLoad(options) {
    const level = parseInt(options.level) || null;
    this.setData({
      level,
      material: level ? levelToMaterial(level) : '',
      band: level ? levelToBand(level) : '',
    });
    await this.loadEnrollments();
  },

  async onShow() {
    await this.loadEnrollments();
  },

  async loadEnrollments() {
    try {
      const enrollments = await api.getMyEnrollments().catch(() => []);
      this.setData({ enrollments, loading: false });
    } catch (e) {
      this.setData({ loading: false });
    }
  },
});
