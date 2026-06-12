import sys
import os

def main():
    if len(sys.argv) < 2:
        print("ERROR: Missing file path parameter.")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"ERROR: File not found at {file_path}")
        sys.exit(1)

    try:
        from markitdown import MarkItDown
    except ImportError:
        # Graceful signal to the Node.js calling process to trigger high-fidelity mock fallback
        print("PYTHON_DEPENDENCY_ERROR: markitdown library is not installed in the python environment.")
        sys.exit(2)

    try:
        markitdown = MarkItDown()
        result = markitdown.convert(file_path)
        if result and result.text_content:
            print(result.text_content)
        else:
            print("ERROR: Empty text content extracted.")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Extraction failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
