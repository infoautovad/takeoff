import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

const autovadTheme = {
  dark: true,
  colors: {
    background: '#061018',
    surface: '#0e1a22',
    primary: '#1eb6ff',
    secondary: '#7ad4ff',
    accent: '#1eb6ff',
    error: '#ff8b6b',
    info: '#7ad4ff',
    success: '#85ffd0',
    warning: '#ffc36a',
    'on-primary': '#061018',
    'on-secondary': '#061018',
    'on-surface': '#e8eef4',
    'on-background': '#e8eef4',
    'surface-variant': '#132028',
    'on-surface-variant': '#8e9aa6',
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
