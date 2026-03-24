// utils.js

export function getStatusColor(value, warn, critical) {
    if (value >= critical) return '#ef4444';
    if (value >= warn) return '#f59e0b';
    return '#4ade80';
}
