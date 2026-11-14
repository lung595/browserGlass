// DMS's QmlUtils.findSettings: the nearest ancestor that loads and saves values
function findSettings(item) {
    while (item) {
        if (item.saveValue !== undefined && item.loadValue !== undefined)
            return item;
        item = item.parent;
    }
    return null;
}
