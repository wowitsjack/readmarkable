# Getting Started with readmarkable

This guide will help you set up and start using readmarkable to sync your markdown files with your reMarkable device.

## Prerequisites

Before you begin, ensure you have:

- Python 3.8 or higher installed
- A reMarkable device with SSH access enabled
- USB cable or WiFi connection to your reMarkable device

## Step 1: Enable SSH on Your reMarkable

1. On your reMarkable device, go to **Settings** > **Help** > **About**
2. Scroll down and tap on **"Copyrights and licenses"**
3. In the developer menu, enable **SSH**
4. Note down the SSH password displayed

## Step 2: Installation

1. Download and extract the readmarkable release files
2. Open a terminal in the extracted folder
3. Install the required dependencies:
   ```bash
   pip install -r resources/requirements.txt
   ```

## Step 3: First Run

1. Launch the application:
   ```bash
   python resources/main.py
   ```
2. The GUI will open with several tabs

## Step 4: Configure Device Connection

1. Go to the **Device** tab
2. Enter your reMarkable's IP address:
   - USB connection: `10.11.99.1` (default)
   - WiFi connection: Check your router or reMarkable settings
3. Enter the SSH password from Step 1
4. Click **Connect** to test the connection

## Step 5: Set Up Synchronization

1. Go to the **Sync** tab
2. Select your local markdown directory
3. Choose the target directory on your reMarkable
4. Enable desired options:
   - **Auto-sync**: Automatically sync when files change
   - **PDF Conversion**: Convert markdown to PDF before upload
   - **File Watching**: Monitor directory for changes

## Step 6: Start Syncing

1. Click **Start Sync** to begin synchronization
2. Monitor progress in the **Logs** tab
3. Your markdown files will be converted to PDF and uploaded to your reMarkable

## Tips for Success

- Keep markdown files simple for best PDF conversion results
- Use standard markdown formatting
- Avoid complex HTML or custom CSS
- Test with a small number of files first

## Troubleshooting

If you encounter issues, check the **Logs** tab for detailed error messages and refer to the main README.md for troubleshooting guidance.