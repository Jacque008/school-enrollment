const api = require('../../utils/api');

Page({
  data: {
    loading: true,
    submitting: false,
    error: '',
    studentId: null,
    testId: null,
    characters: [],
    currentIndex: 0,
    recognized: [],   // chars marked as known
    unknown: [],      // chars marked as unknown
    finished: false,
    result: null,
  },

  async onLoad(options) {
    this.setData({ studentId: options.studentId });
    await this.loadTest();
  },

  async loadTest() {
    this.setData({ loading: true });
    try {
      const data = await api.get('/literacy-test/current');
      this.setData({
        testId: data.id,
        characters: data.characters,
        loading: false,
        currentIndex: 0,
      });
    } catch (e) {
      this.setData({ error: '加载测试失败', loading: false });
    }
  },

  onKnow() {
    const { characters, currentIndex, recognized } = this.data;
    recognized.push(characters[currentIndex]);
    this.nextChar(recognized, this.data.unknown);
  },

  onUnknow() {
    const { characters, currentIndex, unknown } = this.data;
    unknown.push(characters[currentIndex]);
    this.nextChar(this.data.recognized, unknown);
  },

  nextChar(recognized, unknown) {
    const { characters, currentIndex } = this.data;
    const next = currentIndex + 1;
    if (next >= characters.length) {
      this.setData({ recognized, unknown, finished: true });
    } else {
      this.setData({ recognized, unknown, currentIndex: next });
    }
  },

  async onSubmit() {
    this.setData({ submitting: true });
    try {
      const result = await api.post('/literacy-test/submit', {
        student_id: this.data.studentId,
        recognized: this.data.recognized,
        total: this.data.characters.length,
      });
      this.setData({ result, submitting: false });
      // Navigate to result page after 2 seconds
      setTimeout(() => {
        wx.navigateTo({
          url: `/pages/result/result?studentId=${this.data.studentId}&level=${result.computed_level}`,
        });
      }, 2000);
    } catch (e) {
      this.setData({ submitting: false, error: '提交失败，请重试' });
    }
  },

  onSkipToResult() {
    wx.navigateTo({
      url: `/pages/result/result?studentId=${this.data.studentId}`,
    });
  },
});
