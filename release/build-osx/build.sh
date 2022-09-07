# pyinstaller打包
echo 'pyinstaller start'
pyinstaller --log-level=DEBUG --distpath='./release/dist' --workpath='./release/build' --noconfirm ./release/build-osx/build.spec
echo 'pyinstaller completed'

echo 'making dmg...'
# 基本信息
APP_NAME='ArchOctopus'
VERSION=$(/usr/libexec/plistbuddy -c Print:CFBundleShortVersionString "./release/dist/${APP_NAME}.app/Contents/Info.plist")
mkdir -p "./release/dist/v${VERSION}"
BACKGROUND_IMG_NAME="background.png"
DMG_BACKGROUND_IMG="./release/build-osx/${BACKGROUND_IMG_NAME}"
VOL_NAME="${APP_NAME}_v${VERSION}"
DMG_TMP="${VOL_NAME}-temp.dmg"
DMG_FINAL="./release/dist/v${VERSION}/${VOL_NAME}.dmg"
STAGING_DIR="./Install"

# 清理文件夹
rm -rf "${STAGING_DIR}" "${DMG_TMP}"

echo "${VOL_NAME}"
echo "${APP_NAME}"
echo "${VERSION}"

# 创建文件夹,拷贝,计算
mkdir -p "${STAGING_DIR}"
cp -rpf "./release/dist/${APP_NAME}.app" "${STAGING_DIR}"
SIZE=$(du -sh ${STAGING_DIR} | sed 's/\([0-9]*\)M\(.*\)/\1/')
SIZE=$(echo "${SIZE}" + 1.0 | bc | awk '{print int($1+0.5)}')
echo "${SIZE}"

# 容错处理
# shellcheck disable=SC2181
if [ $? -ne 0 ]; then
echo "Error: Cannot compute size of staging dir"
exit 1
fi

# 创建临时dmg文件
hdiutil create -srcfolder "${STAGING_DIR}" -volname "${VOL_NAME}" -fs HFS+ \
-fsargs "-c c=64,a=16,e=16" -format UDRW -size "${SIZE}"M "${DMG_TMP}"
echo "Created DMG: ${DMG_TMP}"

# 设置dmg
# shellcheck disable=SC2196
DEVICE=$(hdiutil attach -readwrite -noverify "${DMG_TMP}" | egrep '^/dev/' | sed 1q | awk '{print $1}')
echo "${DEVICE}"
sleep 2

# 增加Applications目录的软链接
echo "Add link to /Applications"
pushd /Volumes/"${VOL_NAME}" || exit 1
ln -s /Applications ./Applications
popd || exit 1

# 拷贝背景图片
mkdir /Volumes/"${VOL_NAME}"/.background
cp "${DMG_BACKGROUND_IMG}" /Volumes/"${VOL_NAME}"/.background/

# 使用applescript设置一系列的窗口属性
echo '
    tell application "Finder"
        tell disk "'"${VOL_NAME}"'"
            open
            set current view of container window to icon view
            set toolbar visible of container window to false
            set statusbar visible of container window to false
            set the bounds of container window to {350, 200, 970, 700}
            set viewOptions to the icon view options of container window
            set arrangement of viewOptions to not arranged
            set icon size of viewOptions to 100
            set background picture of viewOptions to file ".background:'"${BACKGROUND_IMG_NAME}"'"
            set position of item "'"${APP_NAME}"'.app" of container window to {200, 240}
            set position of item "Applications" of container window to {420, 240}
            update without registering applications
            delay 5
            close
        end tell
    end tell
' | osascript

# 修改权限
chmod -Rf go-w /Volumes/"${VOL_NAME}"

# 写入缓冲
sync

# 卸载
hdiutil detach "${DEVICE}"

# 压缩dmg
echo "Creating compressed image"
hdiutil convert "${DMG_TMP}" -format UDZO -imagekey zlib-level=9 -o "${DMG_FINAL}"

# 清理文件夹
rm -rf "${DMG_TMP}"
rm -rf "${STAGING_DIR}"
echo 'Done.'
