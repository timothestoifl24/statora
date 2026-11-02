import { h } from 'vue'
import DefaultTheme from 'vitepress/theme'
import ApiSpec from './ApiSpec.vue'
import ChannelSwitch from './ChannelSwitch.vue'
import DevBanner from './DevBanner.vue'
import './custom.css'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('ApiSpec', ApiSpec)
  },
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      'layout-top': () => h(DevBanner),
      'nav-bar-content-after': () => h(ChannelSwitch),
      'nav-screen-content-after': () => h(ChannelSwitch),
    }),
}
