import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader, type GLTF } from 'three/addons/loaders/GLTFLoader.js'
import type { ViewerHandle } from '@/types'

function disposeObject3D(object3D: THREE.Object3D) {
  object3D.traverse((child) => {
    const mesh = child as THREE.Mesh
    if (mesh.isMesh) {
      mesh.geometry?.dispose()
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      materials.forEach((material) => material?.dispose())
    }
  })
}

interface ThreeViewerProps {
  onStatusChange: (msg: string) => void
  onRotationChange: (msg: string) => void
  onModelLoaded: () => void
}

const ThreeViewer = forwardRef<ViewerHandle, ThreeViewerProps>(
  ({ onStatusChange, onRotationChange, onModelLoaded }, ref) => {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const wrapRef = useRef<HTMLDivElement>(null)

    // Store mutable scene objects in refs so they persist across renders
    const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
    const sceneRef = useRef<THREE.Scene | null>(null)
    const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
    const controlsRef = useRef<OrbitControls | null>(null)
    const loaderRef = useRef<GLTFLoader>(new GLTFLoader())
    const currentModelRef = useRef<THREE.Object3D | null>(null)
    const animFrameRef = useRef<number>(0)
    const userInteractingRef = useRef(false)
    const rotationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    const onStatusChangeRef = useRef(onStatusChange)
    const onRotationChangeRef = useRef(onRotationChange)
    const onModelLoadedRef = useRef(onModelLoaded)

    useEffect(() => {
      onStatusChangeRef.current = onStatusChange
      onRotationChangeRef.current = onRotationChange
      onModelLoadedRef.current = onModelLoaded
    }, [onModelLoaded, onRotationChange, onStatusChange])

    // ── helpers ───────────────────────────────────────────────────────────────

    function disposeCurrentModel() {
      if (!currentModelRef.current || !sceneRef.current) return
      disposeObject3D(currentModelRef.current)
      sceneRef.current.remove(currentModelRef.current)
      currentModelRef.current = null
    }

    function centerAndFrame(object3D: THREE.Object3D) {
      const camera = cameraRef.current!
      const controls = controlsRef.current!
      const box = new THREE.Box3().setFromObject(object3D)
      const size = new THREE.Vector3()
      const center = new THREE.Vector3()
      box.getSize(size)
      box.getCenter(center)

      object3D.position.x -= center.x
      object3D.position.y -= box.min.y
      object3D.position.z -= center.z

      const maxDim = Math.max(size.x, size.y, size.z) || 1
      const dist = maxDim * 2.3
      camera.position.set(dist * 1.05, dist * 0.78, dist * 1.08)
      controls.target.set(0, size.y * 0.45, 0)
      controls.minDistance = Math.max(maxDim * 0.7, 0.4)
      controls.maxDistance = Math.max(maxDim * 7, 5)
      controls.update()
    }

    function normalizeMaterial(mesh: THREE.Mesh) {
      const count = Array.isArray(mesh.material) ? mesh.material.length : 1
      const unified = Array.from({ length: count }, () =>
        new THREE.MeshStandardMaterial({ color: 0xbfbfbf, roughness: 0.88, metalness: 0.0 })
      )
      mesh.material = Array.isArray(mesh.material) ? unified : unified[0]
    }

    async function loadGLBFromUrl(url: string) {
      const gltf = await new Promise<GLTF>((resolve, reject) => {
        loaderRef.current.load(url, resolve, undefined, reject)
      })
      disposeCurrentModel()
      currentModelRef.current = gltf.scene
      currentModelRef.current.traverse((child) => {
        const mesh = child as THREE.Mesh
        if (mesh.isMesh) {
          normalizeMaterial(mesh)
          mesh.castShadow = false
          mesh.receiveShadow = false
        }
      })
      sceneRef.current!.add(currentModelRef.current)
      centerAndFrame(currentModelRef.current)
      onModelLoadedRef.current()
    }

    // ── exposed handle ────────────────────────────────────────────────────────

    useImperativeHandle(ref, () => ({
      async loadGLBFromUrl(url: string, successMessage = '3D model loaded') {
        try {
          await loadGLBFromUrl(url)
          onStatusChangeRef.current(successMessage)
          return true
        } catch {
          onStatusChangeRef.current('Model could not load')
          return false
        }
      },
      clearModel() {
        disposeCurrentModel()
      },
    }))

    // ── scene setup ───────────────────────────────────────────────────────────

    useEffect(() => {
      const canvas = canvasRef.current!
      const wrap = wrapRef.current!

      const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false })
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
      renderer.outputColorSpace = THREE.SRGBColorSpace
      rendererRef.current = renderer

      const scene = new THREE.Scene()
      scene.background = new THREE.Color(0xf2f1ee)
      sceneRef.current = scene

      const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 1000)
      camera.position.set(2.8, 1.9, 2.9)
      cameraRef.current = camera

      const controls = new OrbitControls(camera, renderer.domElement)
      controls.enableDamping = true
      controls.enablePan = false
      controls.autoRotate = true
      controls.autoRotateSpeed = 1.1
      controls.target.set(0, 0.85, 0)
      controlsRef.current = controls

      controls.addEventListener('start', () => {
        userInteractingRef.current = true
        controls.autoRotate = false
        onRotationChangeRef.current('Auto rotate paused')
      })
      controls.addEventListener('end', () => {
        userInteractingRef.current = false
        if (rotationTimerRef.current) clearTimeout(rotationTimerRef.current)
        rotationTimerRef.current = setTimeout(() => {
          if (!userInteractingRef.current) {
            controls.autoRotate = true
            onRotationChangeRef.current('Auto rotate on')
          }
        }, 1200)
      })

      // Lights
      scene.add(new THREE.AmbientLight(0xffffff, 2.2))
      const hemi = new THREE.HemisphereLight(0xffffff, 0xe0e0dc, 2.0)
      hemi.position.set(0, 8, 0)
      scene.add(hemi)
      const addDir = (color: number, intensity: number, x: number, y: number, z: number) => {
        const l = new THREE.DirectionalLight(color, intensity)
        l.position.set(x, y, z)
        scene.add(l)
      }
      addDir(0xffffff, 2.0, 5, 8, 6)
      addDir(0xffffff, 1.3, -5, 4, 3)
      addDir(0xffffff, 1.2, 0, 3, 8)
      addDir(0xffffff, 0.9, 0, 5, -7)

      // Floor + grid
      const floor = new THREE.Mesh(
        new THREE.PlaneGeometry(20, 20),
        new THREE.MeshBasicMaterial({ color: 0xeaeae7 })
      )
      floor.rotation.x = -Math.PI / 2
      scene.add(floor)
      const grid = new THREE.GridHelper(20, 40, 0xc8c8c3, 0xd8d8d3)
      grid.position.y = 0.001
      scene.add(grid)

      // Resize
      const resize = () => {
        const rect = wrap.getBoundingClientRect()
        const width = Math.max(rect.width, 1)
        const height = Math.max(rect.height, 1)
        renderer.setSize(width, height, false)
        camera.aspect = width / height
        camera.updateProjectionMatrix()
      }
      resize()
      window.addEventListener('resize', resize)

      // Animate
      const animate = () => {
        animFrameRef.current = requestAnimationFrame(animate)
        controls.update()
        renderer.render(scene, camera)
      }
      animate()

      return () => {
        cancelAnimationFrame(animFrameRef.current)
        window.removeEventListener('resize', resize)
        if (rotationTimerRef.current) clearTimeout(rotationTimerRef.current)
        disposeObject3D(scene)
        controls.dispose()
        renderer.dispose()
      }
    }, [])

    return (
      <div ref={wrapRef} className="relative w-full h-full">
        <canvas ref={canvasRef} className="w-full h-full block" />
      </div>
    )
  }
)

ThreeViewer.displayName = 'ThreeViewer'
export default ThreeViewer
