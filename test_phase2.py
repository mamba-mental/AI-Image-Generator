import os
import sys
import tkinter as tk
from PIL import Image

# Add assertion helper
def test_assert(condition, message):
    if not condition:
        print(f"TEST FAILED: {message}")
        return False
    return True

# Create a test image for img2img testing
def create_test_image(path, size=(512, 512)):
    img = Image.new('RGB', size, color=(100, 150, 200))
    img.save(path)
    return path

def run_tests():
    print("Running Phase 2 tests...")
    success = True
    
    # Import app (only after tkinter root is ready)
    from app import ImageGeneratorGUI, ParameterSections, ImageUploader
    
    # Test 1: ParameterSections class
    print("Test 1: ParameterSections class...")
    root = tk.Tk()
    root.withdraw()  # Hide the root window
    
    # Create a frame to hold the parameter sections
    frame = tk.Frame(root)
    
    # Instantiate ParameterSections
    try:
        param_sections = ParameterSections(frame)
        success = test_assert(param_sections is not None, 
                             "ParameterSections instantiation failed") and success
        
        # Test if sections were created
        basic_section = param_sections.get_section("basic")
        advanced_section = param_sections.get_section("advanced")
        experimental_section = param_sections.get_section("experimental")
        
        success = test_assert(basic_section is not None, 
                             "Basic section not created") and success
        success = test_assert(advanced_section is not None, 
                             "Advanced section not created") and success
        success = test_assert(experimental_section is not None, 
                             "Experimental section not created") and success
        
        print("ParameterSections test completed.")
    except Exception as e:
        print(f"ParameterSections test failed with error: {e}")
        success = False
    
    # Test 2: ImageUploader class
    print("\nTest 2: ImageUploader class...")
    try:
        # Create a test image
        test_img_path = create_test_image("test_upload.png")
        
        # Instantiate ImageUploader
        uploader = ImageUploader(frame)
        success = test_assert(uploader is not None, 
                             "ImageUploader instantiation failed") and success
        
        # Test methods
        uploader.load_image(test_img_path)
        success = test_assert(uploader.image_path == test_img_path, 
                             "Image path not set correctly") and success
        
        # Test get_image_path
        returned_path = uploader.get_image_path()
        success = test_assert(returned_path == test_img_path, 
                             "get_image_path not returning correct path") and success
        
        # Test clear
        uploader.clear_image()
        success = test_assert(uploader.image_path is None, 
                             "clear_image not working") and success
        
        print("ImageUploader test completed.")
        
        # Clean up
        if os.path.exists(test_img_path):
            os.remove(test_img_path)
            
    except Exception as e:
        print(f"ImageUploader test failed with error: {e}")
        success = False
    
    # Test 3: Verify app class has the required attributes (without instantiating)
    print("\nTest 3: Verifying app class attributes...")
    try:
        # Check if the ImageGeneratorGUI has the methods for handling our new components
        methods = dir(ImageGeneratorGUI)
        
        # Check for required methods
        required_methods = [
            "create_image_uploader",
            "create_parameters_section",
        ]
        
        for method in required_methods:
            has_method = method in methods
            success = test_assert(has_method, f"Required method {method} not found") and success
            
        # Check if the constructor references our components
        import inspect
        constructor_source = inspect.getsource(ImageGeneratorGUI.__init__)
        has_image_uploader_ref = "create_image_uploader" in constructor_source
        has_parameter_sections_ref = "create_parameters_section" in constructor_source
        
        success = test_assert(has_image_uploader_ref, 
                             "Image uploader not referenced in constructor") and success
        success = test_assert(has_parameter_sections_ref, 
                             "create_parameters_section not referenced in constructor") and success
        
        print("App class verification completed.")
    except Exception as e:
        print(f"App class verification failed with error: {e}")
        success = False
    
    # Display final result
    if success:
        print("\nAll Phase 2 tests PASSED!")
    else:
        print("\nSome Phase 2 tests FAILED! Check output for details.")
        
    # Destroy tkinter root
    root.destroy()
    
    return success

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
