#!/usr/bin/env python3
"""
JavaScript Validation Test
Check if the JavaScript file has syntax errors
"""

import requests
import re

def validate_javascript():
    print("🔍 JavaScript Validation Test")
    print("=" * 40)
    
    try:
        # Get the JavaScript file
        response = requests.get('http://localhost:8000/static/js/app.js', timeout=10)
        
        if response.status_code != 200:
            print(f"❌ Failed to load JavaScript: {response.status_code}")
            return
        
        js_content = response.text
        
        print("✅ JavaScript file loaded successfully")
        
        # Check for common syntax issues
        issues = []
        
        # Check for unclosed brackets
        open_braces = js_content.count('{')
        close_braces = js_content.count('}')
        if open_braces != close_braces:
            issues.append(f"Unmatched braces: {open_braces} open, {close_braces} close")
        
        # Check for unclosed parentheses
        open_parens = js_content.count('(')
        close_parens = js_content.count(')')
        if open_parens != close_parens:
            issues.append(f"Unmatched parentheses: {open_parens} open, {close_parens} close")
        
        # Check for unclosed brackets
        open_brackets = js_content.count('[')
        close_brackets = js_content.count(']')
        if open_brackets != close_brackets:
            issues.append(f"Unmatched brackets: {open_brackets} open, {close_brackets} close")
        
        # Check for syntax errors around line 269
        lines = js_content.split('\n')
        if len(lines) > 269:
            line_269 = lines[268]  # 0-indexed
            print(f"Line 269: {line_269.strip()}")
            
            # Check for common syntax issues in this line
            if 'action: action:' in line_269:
                issues.append("Double 'action:' found on line 269")
            if 'command, command' in line_269:
                issues.append("Duplicate 'command' found on line 269")
        
        # Check for TypeScript syntax
        if 'action:' in js_content and 'command:' in js_content:
            # Look for TypeScript-like syntax
            ts_patterns = [
                r'action:\s*command',
                r'function\s+\w+\([^)]*):\s*[^{]',
                r'let\s+\w+:\s*[^=]',
            ]
            
            for pattern in ts_patterns:
                if re.search(pattern, js_content):
                    issues.append(f"TypeScript syntax found: {pattern}")
        
        # Report results
        if issues:
            print("❌ JavaScript validation issues found:")
            for issue in issues:
                print(f"   • {issue}")
        else:
            print("✅ No JavaScript syntax issues found")
        
        # Check for key functions
        key_functions = [
            'connectToServer',
            'disconnectFromServer', 
            'executeAction',
            'setupEventListeners',
            'init'
        ]
        
        missing_functions = []
        for func in key_functions:
            if f'function {func}' not in js_content and f'{func}(' not in js_content:
                missing_functions.append(func)
        
        if missing_functions:
            print(f"⚠️  Missing functions: {missing_functions}")
        else:
            print("✅ All key functions found")
        
        print(f"📊 JavaScript file size: {len(js_content)} characters")
        print(f"📊 Total lines: {len(lines)}")
        
    except Exception as e:
        print(f"❌ JavaScript validation failed: {e}")

if __name__ == "__main__":
    validate_javascript()
