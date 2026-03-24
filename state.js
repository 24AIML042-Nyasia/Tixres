// state.js
import { CONFIG } from './config.js';

export const state = {
    charts: {
        cpu: {
            ctx: null,
            data: [],
            maxPoints: CONFIG.CHART_HISTORY_POINTS
        },
        memoryStack: {
            ctx: null
        },
        network: {
            ctx: null,
            uploadData: [],
            downloadData: [],
            maxPoints: CONFIG.CHART_HISTORY_POINTS
        }
    },
    lastUpdate: null
};
