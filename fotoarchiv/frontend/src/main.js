import { mount } from 'svelte';
import App from './App.svelte';
import './app.css';
import { applyTheme, readTheme } from './lib/theme.js';

applyTheme(readTheme());

mount(App, { target: document.getElementById('app') });
