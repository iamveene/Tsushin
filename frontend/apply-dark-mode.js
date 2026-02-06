/**
 * Dark Mode Converter Script
 * Systematically applies dark mode classes to all TSX files
 */

const fs = require('fs');
const path = require('path');

// Color mapping from light to dark with proper Tailwind dark: prefix
const colorMap = [
  // Backgrounds
  { from: /bg-white(?![\w-])/g, to: 'bg-white dark:bg-gray-800' },
  { from: /bg-gray-50(?![\w-])/g, to: 'bg-gray-50 dark:bg-gray-900' },
  { from: /bg-gray-100(?![\w-])/g, to: 'bg-gray-100 dark:bg-gray-800' },
  { from: /bg-gray-200(?![\w-])/g, to: 'bg-gray-200 dark:bg-gray-700' },
  { from: /bg-gray-300(?![\w-])/g, to: 'bg-gray-300 dark:bg-gray-600' },

  // Text colors
  { from: /text-gray-900(?![\w-])/g, to: 'text-gray-900 dark:text-gray-100' },
  { from: /text-gray-800(?![\w-])/g, to: 'text-gray-800 dark:text-gray-200' },
  { from: /text-gray-700(?![\w-])/g, to: 'text-gray-700 dark:text-gray-300' },
  { from: /text-gray-600(?![\w-])/g, to: 'text-gray-600 dark:text-gray-400' },
  { from: /text-gray-500(?![\w-])/g, to: 'text-gray-500 dark:text-gray-400' },

  // Borders
  { from: /border-gray-200(?![\w-])/g, to: 'border-gray-200 dark:border-gray-700' },
  { from: /border-gray-300(?![\w-])/g, to: 'border-gray-300 dark:border-gray-600' },
  { from: /border(?![\w-])/g, to: 'border dark:border-gray-700' },

  // Colored backgrounds (info boxes, status indicators)
  { from: /bg-blue-50(?![\w-])/g, to: 'bg-blue-50 dark:bg-blue-900/20' },
  { from: /bg-blue-100(?![\w-])/g, to: 'bg-blue-100 dark:bg-blue-800/30' },
  { from: /bg-green-50(?![\w-])/g, to: 'bg-green-50 dark:bg-green-900/20' },
  { from: /bg-green-100(?![\w-])/g, to: 'bg-green-100 dark:bg-green-800/30' },
  { from: /bg-green-200(?![\w-])/g, to: 'bg-green-200 dark:bg-green-700/40' },
  { from: /bg-yellow-50(?![\w-])/g, to: 'bg-yellow-50 dark:bg-yellow-900/20' },
  { from: /bg-yellow-100(?![\w-])/g, to: 'bg-yellow-100 dark:bg-yellow-800/30' },
  { from: /bg-yellow-200(?![\w-])/g, to: 'bg-yellow-200 dark:bg-yellow-700/40' },
  { from: /bg-red-50(?![\w-])/g, to: 'bg-red-50 dark:bg-red-900/20' },
  { from: /bg-red-100(?![\w-])/g, to: 'bg-red-100 dark:bg-red-800/30' },
  { from: /bg-purple-50(?![\w-])/g, to: 'bg-purple-50 dark:bg-purple-900/20' },
  { from: /bg-purple-100(?![\w-])/g, to: 'bg-purple-100 dark:bg-purple-800/30' },
  { from: /bg-purple-200(?![\w-])/g, to: 'bg-purple-200 dark:bg-purple-700/40' },
  { from: /bg-orange-50(?![\w-])/g, to: 'bg-orange-50 dark:bg-orange-900/20' },

  // Colored text
  { from: /text-blue-800(?![\w-])/g, to: 'text-blue-800 dark:text-blue-200' },
  { from: /text-blue-700(?![\w-])/g, to: 'text-blue-700 dark:text-blue-300' },
  { from: /text-green-800(?![\w-])/g, to: 'text-green-800 dark:text-green-200' },
  { from: /text-green-700(?![\w-])/g, to: 'text-green-700 dark:text-green-300' },
  { from: /text-yellow-800(?![\w-])/g, to: 'text-yellow-800 dark:text-yellow-200' },
  { from: /text-yellow-700(?![\w-])/g, to: 'text-yellow-700 dark:text-yellow-300' },
  { from: /text-purple-800(?![\w-])/g, to: 'text-purple-800 dark:text-purple-200' },
  { from: /text-purple-700(?![\w-])/g, to: 'text-purple-700 dark:text-purple-300' },
  { from: /text-purple-900(?![\w-])/g, to: 'text-purple-900 dark:text-purple-100' },
  { from: /text-red-700(?![\w-])/g, to: 'text-red-700 dark:text-red-300' },

  // Colored borders
  { from: /border-blue-200(?![\w-])/g, to: 'border-blue-200 dark:border-blue-700' },
  { from: /border-blue-300(?![\w-])/g, to: 'border-blue-300 dark:border-blue-600' },
  { from: /border-green-200(?![\w-])/g, to: 'border-green-200 dark:border-green-700' },
  { from: /border-green-300(?![\w-])/g, to: 'border-green-300 dark:border-green-600' },
  { from: /border-yellow-200(?![\w-])/g, to: 'border-yellow-200 dark:border-yellow-700' },
  { from: /border-purple-200(?![\w-])/g, to: 'border-purple-200 dark:border-purple-700' },
  { from: /border-purple-300(?![\w-])/g, to: 'border-purple-300 dark:border-purple-600' },

  // Hover states
  { from: /hover:bg-gray-50(?![\w-])/g, to: 'hover:bg-gray-50 dark:hover:bg-gray-700' },
  { from: /hover:bg-gray-100(?![\w-])/g, to: 'hover:bg-gray-100 dark:hover:bg-gray-700' },
  { from: /hover:bg-blue-200(?![\w-])/g, to: 'hover:bg-blue-200 dark:hover:bg-blue-700' },
  { from: /hover:bg-green-200(?![\w-])/g, to: 'hover:bg-green-200 dark:hover:bg-green-700' },
  { from: /hover:bg-red-200(?![\w-])/g, to: 'hover:bg-red-200 dark:hover:bg-red-700' },
  { from: /hover:bg-yellow-200(?![\w-])/g, to: 'hover:bg-yellow-200 dark:hover:bg-yellow-700' },
  { from: /hover:bg-purple-200(?![\w-])/g, to: 'hover:bg-purple-200 dark:hover:bg-purple-700' },

  // Hover text
  { from: /hover:text-gray-900(?![\w-])/g, to: 'hover:text-gray-900 dark:hover:text-gray-100' },
  { from: /hover:text-gray-800(?![\w-])/g, to: 'hover:text-gray-800 dark:hover:text-gray-200' },
];

function processFile(filePath) {
  try {
    let content = fs.readFileSync(filePath, 'utf8');
    let modified = false;

    // Skip if file already has many dark: classes
    const darkCount = (content.match(/dark:/g) || []).length;
    if (darkCount > 20) {
      console.log(`⏭️  Skipping ${filePath} (already has ${darkCount} dark: classes)`);
      return;
    }

    // Apply color mappings
    colorMap.forEach(({ from, to }) => {
      const before = content;
      content = content.replace(from, to);
      if (content !== before) {
        modified = true;
      }
    });

    if (modified) {
      fs.writeFileSync(filePath, content, 'utf8');
      console.log(`✅ Updated ${filePath}`);
    } else {
      console.log(`⏭️  No changes needed for ${filePath}`);
    }
  } catch (error) {
    console.error(`❌ Error processing ${filePath}:`, error.message);
  }
}

function processDirectory(dir) {
  const files = fs.readdirSync(dir, { withFileTypes: true });

  files.forEach(file => {
    const fullPath = path.join(dir, file.name);

    if (file.isDirectory() && !file.name.startsWith('.') && file.name !== 'node_modules') {
      processDirectory(fullPath);
    } else if (file.isFile() && file.name.endsWith('.tsx')) {
      processFile(fullPath);
    }
  });
}

// Start processing
console.log('🌙 Starting Dark Mode Conversion...\n');

const appDir = path.join(__dirname, 'app');
const componentsDir = path.join(__dirname, 'components');

if (fs.existsSync(appDir)) {
  console.log('📁 Processing app directory...');
  processDirectory(appDir);
}

if (fs.existsSync(componentsDir)) {
  console.log('\n📁 Processing components directory...');
  processDirectory(componentsDir);
}

console.log('\n✨ Dark Mode Conversion Complete!');
console.log('\n💡 Note: Some manual adjustments may be needed for:');
console.log('   - Complex gradient backgrounds');
console.log('   - Custom color combinations');
console.log('   - SVG/Image filters');
