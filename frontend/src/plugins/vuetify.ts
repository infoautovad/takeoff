import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

const autovadTheme = {
  dark: true,
  colors: {
    background: '#07100e',
    surface: '#101f1a',
    primary: '#d9ff43',
    secondary: '#85ffd0',
    accent: '#d9ff43',
    error: '#ff8b6b',
    info: '#85ffd0',
    success: '#85ffd0',
    warning: '#ffc36a',
    'on-primary': '#12190c',
    'on-secondary': '#07100e',
    'on-surface': '#eaf0eb',
    'on-background': '#eaf0eb',
    'surface-variant': '#15231e',
    'on-surface-variant': '#8e9b94',
  },
}

export default createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'autovadTheme',
    themes: {
      autovadTheme,
    },
  },
  defaults: {
    VBtn: {
      rounded: 0,
      elevation: 0,
    },
    VCard: {
      rounded: 0,
      elevation: 0,
    },
    VChip: {
      rounded: 0,
    },
    VTextField: {
      variant: 'outlined',
      density: 'comfortable',
      color: 'primary',
    },
    VSelect: {
      variant: 'outlined',
      density: 'comfortable',
      color: 'primary',
    },
    VTextarea: {
      variant: 'outlined',
      density: 'comfortable',
      color: 'primary',
    },
    VTabs: {
      color: 'primary',
    },
  },
})
