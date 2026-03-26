const api = require('../../utils/api');

Page({
  data: {
    step: 1,
    totalSteps: 6,
    loading: false,
    error: '',
    semester: null,

    // Form data
    student: {
      name: '',
      gender: 'male',
      birth_date: '',
      city_region: '',
      nationality: '',
    },
    guardian: {
      name: '',
      email: '',
      phone: '',
      wechat_id: '',
      relationship_to_child: 'mom',
      gender: 'female',
      nationality: '',
      language: '',
    },
    relationshipLabel: '妈妈',
    siblings: [],        // [{name:'', class_name:''}]
    hasSibling: false,
    schedule: {
      slot_types: [],
    },
    homeLanguageLabel: '主要说中文',
    // Object maps for WXML checkbox binding (WXML doesn't support .includes())
    slotSelected: {},
    interestSelected: {},
    habitSelected: {},
    proficiency: {
      listening_level: 2,
      speaking_level: 2,
      writing_level: 1,
    },
    literacy: {
      pinyin_level: 1,
      vocab_level: 2,
      reading_interest: [],
      reading_ability: 'needs_help',
      reading_habits: [],
    },
    background: {
      home_language: 'chinese',
      learning_history: '',
      other_hobbies: '',
      parent_expectations: '',
      school_feedback: '',
      other_notes: '',
      referral_source: '',
      accept_alternative: true,
    },

    // Options
    slotOptions: [
      { value: 'sat_onsite_am', label: '周六 Sollentuna 实体课 - 上午 9:30 - 11:30' },
      { value: 'sat_onsite_noon', label: '周六 Sollentuna 实体课 - 中午 12:30 - 14:30' },
      { value: 'sat_onsite_pm', label: '周六 Sollentuna 实体课 - 下午 15:00 - 17:00' },
      { value: 'weekend_online_am', label: '周六/周日 网课 - 上午 9:30 - 11:30' },
      { value: 'weekend_online_noon', label: '周六/周日 网课 - 中午 12:30 - 14:30' },
      { value: 'weekend_online_pm', label: '周六/周日 网课 - 下午 15:00 - 17:00' },
      { value: 'mini_online', label: '迷你线上中文课（1对1~1对3）' },
    ],
    listeningOptions: [
      '听不懂',
      '听得懂一些日常用语',
      '能听得懂儿童故事',
      '基本听得懂所有中文对话和书面用语',
    ],
    speakingOptions: [
      '基本不说',
      '能够简单对话',
      '能够日常对话，但表达不够清晰准确',
      '日常对话清晰准确',
      '口头表达逻辑性强、用词准确丰富',
    ],
    writingOptions: [
      '不会',
      '刚开始练',
      '会写几个字',
      '会造简单的句子',
      '会写简单的作文',
      '能写内容丰富的文章',
    ],
    pinyinOptions: ['不会', '刚开始学或会一部分', '能够准确使用'],
    vocabOptions: [
      '不识字',
      '认识几十个字',
      '可以读带拼音的儿童书',
      '能够读不带拼音的书，但有不少生字',
      '能够独立阅读各种中文书，很少有生字',
    ],
    readingInterestOptions: [
      '不喜欢看书',
      '喜欢看瑞典文书，不喜欢中文书',
      '喜欢读儿童绘本',
      '喜欢读以文字为主的书',
    ],
    readingHabitOptions: [
      '边读边做其它事',
      '能长时间安静看书',
      '爱朗读',
    ],
    languageOptions: [
      { value: 'chinese', label: '中文' },
      { value: 'swedish', label: '瑞典语' },
      { value: 'mixed', label: '中瑞混合' },
      { value: 'other', label: '其他' },
    ],
    relationshipOptions: [
      { value: 'mom', label: '妈妈' },
      { value: 'dad', label: '爸爸' },
      { value: 'other', label: '其他' },
    ],
  },

  async onLoad() {
    // Step 1: WeChat login to get/create guardian token
    try {
      const { code } = await new Promise((res, rej) =>
        wx.login({ success: res, fail: rej })
      );
      const { access_token } = await api.wechatLogin(code);
      getApp().globalData.token = access_token;
      wx.setStorageSync('token', access_token);
    } catch (e) {
      console.error('登录失败', e);
      this.setData({ error: '微信登录失败，请重试' });
      return;
    }
    // Step 2: Load semester info
    try {
      const semester = await api.getCurrentSemester();
      this.setData({ semester });
    } catch (e) {
      this.setData({ error: '无法获取学期信息，请稍后重试' });
    }
  },

  // Navigation
  nextStep() {
    if (!this.validateCurrentStep()) return;
    if (this.data.step < this.data.totalSteps) {
      this.setData({ step: this.data.step + 1, error: '' });
    }
  },

  prevStep() {
    if (this.data.step > 1) {
      this.setData({ step: this.data.step - 1, error: '' });
    }
  },

  validateCurrentStep() {
    const { step, student, guardian, schedule } = this.data;
    switch (step) {
      case 1:
        if (!student.name || !student.birth_date || !student.city_region) {
          this.setData({ error: '请填写所有必填项' });
          return false;
        }
        break;
      case 2:
        if (!guardian.name) {
          this.setData({ error: '请填写监护人姓名' });
          return false;
        }
        if (!guardian.wechat_id) {
          this.setData({ error: '请填写微信号（用于加入班级家长群）' });
          return false;
        }
        break;
      case 3:
        if (schedule.slot_types.length === 0) {
          this.setData({ error: '请至少选择一个上课时段' });
          return false;
        }
        break;
    }
    return true;
  },

  // Step 1 handlers
  onStudentInput(e) {
    const { field } = e.currentTarget.dataset;
    this.setData({ [`student.${field}`]: e.detail.value });
  },
  onGenderChange(e) {
    this.setData({ 'student.gender': e.detail.value === '0' ? 'male' : 'female' });
  },
  onBirthDateChange(e) {
    this.setData({ 'student.birth_date': e.detail.value });
  },

  // Step 2 handlers
  onGuardianInput(e) {
    const { field } = e.currentTarget.dataset;
    this.setData({ [`guardian.${field}`]: e.detail.value });
  },
  onSiblingChange(e) {
    const has = e.detail.value;
    this.setData({
      hasSibling: has,
      siblings: has ? [{ name: '', class_name: '' }] : [],
    });
  },
  onSiblingInput(e) {
    const { index, field } = e.currentTarget.dataset;
    this.setData({ [`siblings[${index}].${field}`]: e.detail.value });
  },
  onAddSibling() {
    this.setData({ siblings: [...this.data.siblings, { name: '', class_name: '' }] });
  },
  onRemoveSibling(e) {
    const { index } = e.currentTarget.dataset;
    const siblings = this.data.siblings.filter((_, i) => i !== index);
    this.setData({ siblings, hasSibling: siblings.length > 0 });
  },

  // Step 3 handlers
  onSlotToggle(e) {
    const { value } = e.currentTarget.dataset;
    const slots = [...this.data.schedule.slot_types];
    const selected = Object.assign({}, this.data.slotSelected);
    const idx = slots.indexOf(value);
    if (idx >= 0) {
      slots.splice(idx, 1);
      selected[value] = false;
    } else {
      slots.push(value);
      selected[value] = true;
    }
    this.setData({ 'schedule.slot_types': slots, slotSelected: selected });
  },

  // Step 4 handlers
  onListeningChange(e) {
    this.setData({ 'proficiency.listening_level': +e.detail.value + 1 });
  },
  onSpeakingChange(e) {
    this.setData({ 'proficiency.speaking_level': +e.detail.value + 1 });
  },
  onWritingChange(e) {
    this.setData({ 'proficiency.writing_level': +e.detail.value + 1 });
  },

  // Step 5 handlers
  onPinyinChange(e) {
    this.setData({ 'literacy.pinyin_level': +e.detail.value + 1 });
  },
  onVocabChange(e) {
    this.setData({ 'literacy.vocab_level': +e.detail.value + 1 });
  },
  onReadingInterestToggle(e) {
    const { value } = e.currentTarget.dataset;
    const arr = [...this.data.literacy.reading_interest];
    const selected = Object.assign({}, this.data.interestSelected);
    const idx = arr.indexOf(value);
    if (idx >= 0) { arr.splice(idx, 1); selected[value] = false; }
    else { arr.push(value); selected[value] = true; }
    this.setData({ 'literacy.reading_interest': arr, interestSelected: selected });
  },
  onReadingAbilityChange(e) {
    this.setData({
      'literacy.reading_ability': e.detail.value === '0' ? 'independent' : 'needs_help',
    });
  },
  onReadingHabitToggle(e) {
    const { value } = e.currentTarget.dataset;
    const arr = [...this.data.literacy.reading_habits];
    const selected = Object.assign({}, this.data.habitSelected);
    const idx = arr.indexOf(value);
    if (idx >= 0) { arr.splice(idx, 1); selected[value] = false; }
    else { arr.push(value); selected[value] = true; }
    this.setData({ 'literacy.reading_habits': arr, habitSelected: selected });
  },

  // Step 6 handlers
  onBackgroundInput(e) {
    const { field } = e.currentTarget.dataset;
    this.setData({ [`background.${field}`]: e.detail.value });
  },
  onLanguageChange(e) {
    const { value, label } = e.currentTarget.dataset;
    this.setData({
      'background.home_language': value,
      homeLanguageLabel: label,
    });
  },
  onRelationshipChange(e) {
    const { value, label } = e.currentTarget.dataset;
    const gender = value === 'mom' ? 'female' : value === 'dad' ? 'male' : '';
    this.setData({
      'guardian.relationship_to_child': value,
      'guardian.gender': gender,
      relationshipLabel: label,
    });
  },
  onAcceptAlternativeChange(e) {
    this.setData({ 'background.accept_alternative': e.detail.value });
  },

  async onSubmit() {
    this.setData({ loading: true, error: '' });
    try {
      const validSiblings = this.data.siblings.filter(s => s.name.trim());
      const sibling_info = validSiblings
        .map(s => s.class_name ? `${s.name}：${s.class_name}` : s.name)
        .join('、');
      const payload = {
        student: {
          ...this.data.student,
          birth_date: this.data.student.birth_date
            ? this.data.student.birth_date + '-01'
            : '',
        },
        guardian: {
          ...this.data.guardian,
          sibling_in_school: validSiblings.length > 0,
          sibling_info,
        },
        schedule: this.data.schedule,
        proficiency: this.data.proficiency,
        literacy: this.data.literacy,
        background: this.data.background,
      };

      const result = await api.submitRegistration(payload);
      console.log('注册成功，result:', JSON.stringify(result));
      this.setData({ loading: false });

      wx.showModal({
        title: '报名成功！',
        content: '是否参加识字量测试？测试结果将用于更精准的分班建议。',
        confirmText: '参加测试',
        cancelText: '跳过',
        success: (res) => {
          console.log('modal success:', res.confirm);
          if (res.confirm) {
            wx.navigateTo({
              url: `/pages/test/test?studentId=${result.id}`,
            });
          } else {
            wx.navigateTo({
              url: `/pages/result/result?studentId=${result.id}&level=${result.computed_level}`,
            });
          }
        },
        fail: (err) => {
          console.error('showModal fail:', JSON.stringify(err));
        },
      });
    } catch (e) {
      const msg = e.data?.detail || '提交失败，请检查填写内容后重试';
      this.setData({ error: typeof msg === 'string' ? msg : JSON.stringify(msg) });
    } finally {
      this.setData({ loading: false });
    }
  },
});
