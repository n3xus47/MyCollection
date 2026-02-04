import 'dart:io';
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';
import '../services/api_service.dart';
import '../models/models.dart';

enum ScanMode { mlKit, smart }

class ScannerScreen extends StatefulWidget {
  const ScannerScreen({super.key});

  @override
  State<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends State<ScannerScreen> {
  CameraController? _cameraController;
  final TextRecognizer _textRecognizer = TextRecognizer();
  
  bool _isInitialized = false;
  bool _isProcessing = false;
  bool _isCapturing = false;
  String? _lastProcessedCode;
  ScanMode _scanMode = ScanMode.mlKit;
  String? _detectedCode;
  String _currentMode = 'ML Kit';
  
  // Lista toy_number z bazy danych - używana do budowania wzorców regex
  List<String> _toyNumbers = [];
  Set<String> _toyNumberSet = {};
  bool _toyNumbersLoaded = false;
  
  // Fallback regex pattern (używany jeśli nie udało się załadować z bazy)
  final RegExp _fallbackRegex = RegExp(r'[A-Z0-9]{3,10}');

  @override
  void initState() {
    super.initState();
    _loadToyNumbers();
    _initializeCamera();
  }
  
  Future<void> _loadToyNumbers() async {
    try {
      final toyNumbers = await ApiService.getAllToyNumbers();
      setState(() {
        _toyNumbers = toyNumbers;
        _toyNumberSet = toyNumbers.map((tn) => tn.toUpperCase()).toSet();
        _toyNumbersLoaded = true;
      });
      print('✓ Załadowano ${toyNumbers.length} toy_number z bazy danych');
    } catch (e) {
      print('⚠ Nie udało się załadować toy_number z bazy: $e');
      print('   Używam fallback regex pattern');
      setState(() {
        _toyNumbersLoaded = true; // Ustawiamy na true żeby nie blokować skanowania
      });
    }
  }

  Future<void> _initializeCamera() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        setState(() {
          _isInitialized = false;
        });
        return;
      }

      _cameraController = CameraController(
        cameras[0],
        ResolutionPreset.medium, // Changed from high to reduce format compatibility issues
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.yuv420, // Explicitly set format for better compatibility
      );

      await _cameraController!.initialize();
      await _cameraController!.setFlashMode(FlashMode.off);
      
      setState(() {
        _isInitialized = true;
      });

      _processCameraFrames();
    } catch (e) {
      print('Error initializing camera: $e');
      // Clean up controller if initialization failed
      await _cameraController?.dispose();
      _cameraController = null;
      setState(() {
        _isInitialized = false;
      });
    }
  }

  Future<void> _processCameraFrames() async {
    if (_cameraController == null || !_cameraController!.value.isInitialized) {
      return;
    }

    while (mounted && _isInitialized) {
      if (_isProcessing || _isCapturing) {
        await Future.delayed(const Duration(milliseconds: 200));
        continue;
      }

      try {
        _isCapturing = true;
        final image = await _cameraController!.takePicture();
        _isCapturing = false;
        final imagePath = image.path;

        // Try ML Kit OCR first
        final mlKitResult = await _performOCR(imagePath);
        
        if (mlKitResult != null) {
          // Found code with ML Kit - use it immediately
          if (mlKitResult != _lastProcessedCode) {
            _lastProcessedCode = mlKitResult;
            _handleCodeFound(mlKitResult, null); // No variant matching data from ML Kit
          }
        } else if (_scanMode == ScanMode.smart) {
          // ML Kit didn't find code, try Smart Mode (Gemini)
          final geminiResult = await _trySmartMode(imagePath);
          if (geminiResult != null) {
            final toyNumber = geminiResult['toy_number'] as String?;
            if (toyNumber != null && toyNumber != _lastProcessedCode) {
              _lastProcessedCode = toyNumber;
              _handleCodeFound(toyNumber, geminiResult); // Pass full Gemini data for variant matching
            }
          }
        }

        // Clean up image file
        await _deleteImageFile(imagePath);
      } catch (e) {
        print('Error processing frame: $e');
      }

      await Future.delayed(const Duration(milliseconds: 500));
    }
  }

  Future<String?> _performOCR(String imagePath) async {
    try {
      final inputImage = InputImage.fromFilePath(imagePath);
      final recognizedText = await _textRecognizer.processImage(inputImage);
      
      // Szukaj toy_number na podstawie bazy danych
      for (final block in recognizedText.blocks) {
        for (final line in block.lines) {
          final lineText = line.text.toUpperCase().trim();
          
          // Metoda 1: Sprawdź czy cała linia lub część linii to toy_number z bazy
          if (_toyNumberSet.isNotEmpty) {
            // Sprawdź czy linia zawiera któryś z toy_number
            for (final toyNumber in _toyNumberSet) {
              if (lineText.contains(toyNumber)) {
                // Znaleziono toy_number z bazy - sprawdź czy to nie fałszywy alarm
                // (np. "GTK21" w "GTK21-N521" lub samodzielnie)
                final regex = RegExp(r'\b' + RegExp.escape(toyNumber) + r'\b');
                final match = regex.firstMatch(lineText);
                if (match != null) {
                  // Sprawdź jakość rozpoznania
                  double minX = double.infinity;
                  double maxX = 0;
                  double minY = double.infinity;
                  double maxY = 0;
                  
                  for (final element in line.elements) {
                    final rect = element.boundingBox;
                    minX = minX < rect.left ? minX : rect.left;
                    maxX = maxX > rect.right ? maxX : rect.right;
                    minY = minY < rect.top ? minY : rect.top;
                    maxY = maxY > rect.bottom ? maxY : rect.bottom;
                  }
                  
                  final width = maxX - minX;
                  final height = maxY - minY;
                  
                  // Jeśli tekst ma rozsądny rozmiar, uznaj za prawidłowy
                  if (width > 30 && width < 500 && height > 8 && height < 100) {
                    if (mounted) {
                      setState(() {
                        _detectedCode = toyNumber;
                        _currentMode = 'ML Kit';
                      });
                    }
                    return toyNumber;
                  }
                }
              }
            }
          }
          
          // Metoda 2: Fallback - użyj regex jeśli nie załadowano z bazy
          if (_toyNumberSet.isEmpty) {
            final match = _fallbackRegex.firstMatch(lineText);
            if (match != null) {
              final code = match.group(0)!;
              
              // Sprawdź jakość
              double minX = double.infinity;
              double maxX = 0;
              double minY = double.infinity;
              double maxY = 0;
              
              for (final element in line.elements) {
                final rect = element.boundingBox;
                minX = minX < rect.left ? minX : rect.left;
                maxX = maxX > rect.right ? maxX : rect.right;
                minY = minY < rect.top ? minY : rect.top;
                maxY = maxY > rect.bottom ? maxY : rect.bottom;
              }
              
              final width = maxX - minX;
              final height = maxY - minY;
              
              if (width > 50 && width < 500 && height > 10 && height < 100) {
                if (mounted) {
                  setState(() {
                    _detectedCode = code;
                    _currentMode = 'ML Kit (fallback)';
                  });
                }
                return code;
              }
            }
          }
        }
      }
      
      return null;
    } catch (e) {
      print('Error performing OCR: $e');
      return null;
    }
  }

  Future<Map<String, dynamic>?> _trySmartMode(String imagePath) async {
    try {
      if (mounted) {
        setState(() {
          _currentMode = 'Smart Mode (Gemini)';
        });
      }
      
      final file = File(imagePath);
      final result = await ApiService.extractModelCodeWithGemini(file);
      
      if (result != null && mounted) {
        final toyNumber = result['toy_number'] as String?;
        if (toyNumber != null) {
          setState(() {
            _detectedCode = toyNumber;
          });
        }
      }
      
      return result;
    } catch (e) {
      print('Error in Smart Mode: $e');
      return null;
    }
  }

  Future<void> _handleCodeFound(String code, Map<String, dynamic>? variantData) async {
    if (!mounted || _isProcessing) return;

    setState(() {
      _isProcessing = true;
    });

    try {
      // Extract toy number from model code (e.g., HYW54-N521 -> HYW54)
      final toyNumber = code.split('-').first;
      
      // Extract variant matching parameters from Gemini data if available
      int? year;
      String? series;
      String? color;
      String? seriesNumber;
      
      if (variantData != null) {
        year = variantData['release_year'] as int?;
        series = variantData['series_name'] as String?;
        color = variantData['body_color'] as String?;
        seriesNumber = variantData['series_number'] as String?;
      }
      
      // Call identify with variant matching parameters
      final response = await ApiService.identifyCar(
        toyNumber,
        year: year,
        series: series,
        color: color,
        seriesNumber: seriesNumber,
      );
      
      if (!mounted) return;

      if (response.car.variants.length == 1) {
        await _addToCollection(response.car.variants.first.id);
      } else if (response.car.variants.length > 1) {
        _showVariantSelectionBottomSheet(response.car, response.car.variants);
      } else {
        _showMessage('No variants found for this car');
      }
    } catch (e) {
      if (mounted) {
        _showMessage('Error: $e');
      }
    } finally {
      if (mounted) {
        setState(() {
          _isProcessing = false;
          _lastProcessedCode = null; // Allow scanning same code again
        });
      }
    }
  }

  void _showVariantSelectionBottomSheet(Car car, List<Variant> variants) {
    showModalBottomSheet(
      context: context,
      builder: (context) => Container(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Select Variant',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Text(
              '${car.name} - ${car.brand}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 16),
            ...variants.map((variant) => ListTile(
              title: Text(variant.desc),
              trailing: variant.isChase
                  ? const Chip(
                      label: Text('CHASE', style: TextStyle(fontSize: 10)),
                      backgroundColor: Colors.amber,
                    )
                  : null,
              onTap: () {
                Navigator.pop(context);
                _addToCollection(variant.id);
              },
            )),
          ],
        ),
      ),
    );
  }

  Future<void> _addToCollection(String variantId) async {
    try {
      await ApiService.addToCollection(variantId);
      if (mounted) {
        _showMessage('Added to collection!', isSuccess: true);
      }
    } catch (e) {
      if (mounted) {
        _showMessage('Error adding to collection: $e');
      }
    }
  }

  void _showMessage(String message, {bool isSuccess = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isSuccess ? Colors.green : Colors.red,
        duration: const Duration(seconds: 2),
      ),
    );
  }

  Future<void> _deleteImageFile(String path) async {
    try {
      final file = File(path);
      if (await file.exists()) {
        await file.delete();
      }
    } catch (e) {
      // Ignore deletion errors
    }
  }

  @override
  void dispose() {
    _cameraController?.dispose();
    _cameraController = null;
    _textRecognizer.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_isInitialized) {
      return const Scaffold(
        body: Center(
          child: CircularProgressIndicator(),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Scan Model Code'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        actions: [
          PopupMenuButton<ScanMode>(
            icon: const Icon(Icons.settings),
            onSelected: (ScanMode mode) {
              setState(() {
                _scanMode = mode;
              });
            },
            itemBuilder: (context) => [
              const PopupMenuItem(
                value: ScanMode.mlKit,
                child: Text('ML Kit Only (Free)'),
              ),
              const PopupMenuItem(
                value: ScanMode.smart,
                child: Text('Smart Mode (ML Kit + Gemini)'),
              ),
            ],
          ),
        ],
      ),
      body: Stack(
        children: [
          CameraPreview(_cameraController!),
          
          if (_isProcessing)
            Container(
              color: Colors.black54,
              child: const Center(
                child: CircularProgressIndicator(),
              ),
            ),
          
          // Mode indicator
          Positioned(
            top: 20,
            right: 20,
            child: Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                'Mode: $_currentMode',
                style: const TextStyle(color: Colors.white, fontSize: 12),
              ),
            ),
          ),
          
          Positioned(
            bottom: 20,
            left: 0,
            right: 0,
            child: Container(
              padding: const EdgeInsets.all(16),
              color: Colors.black54,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text(
                    'Point camera at model code (e.g., HYW54-N521)',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  ),
                  const SizedBox(height: 8),
                  if (_detectedCode != null)
                    Text(
                      'Detected: $_detectedCode',
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Colors.green,
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    )
                  else
                    const Text(
                      'Waiting for code...',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: Colors.grey,
                        fontSize: 14,
                      ),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
