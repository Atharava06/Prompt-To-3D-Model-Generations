import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'

interface ModelPreviewProps {
  url: string
}

function disposeObject3D(object3D: THREE.Object3D) {
  object3D.traverse((child) => {
    const mesh = child as THREE.Mesh
    if (!mesh.isMesh) return
    mesh.geometry?.dispose()
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    materials.forEach((material) => material?.dispose())
  })
}

function normalizeMaterial(mesh: THREE.Mesh) {
  const count = Array.isArray(mesh.material) ? mesh.material.length : 1
  const material = Array.from(
    { length: count },
    () => new THREE.MeshStandardMaterial({ color: 0xc8c8c8, roughness: 0.82, metalness: 0.02 }),
  )
  mesh.material = Array.isArray(mesh.material) ? material : material[0]
}

export default function ModelPreview({ url }: ModelPreviewProps) {
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const wrap = wrapRef.current
    if (!wrap) return

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    wrap.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 1000)
    camera.position.set(2.6, 1.8, 2.8)

    scene.add(new THREE.AmbientLight(0xffffff, 2.4))
    const hemi = new THREE.HemisphereLight(0xffffff, 0xced4c6, 2.2)
    hemi.position.set(0, 8, 0)
    scene.add(hemi)
    const key = new THREE.DirectionalLight(0xffffff, 2.4)
    key.position.set(4, 7, 5)
    scene.add(key)
    const fill = new THREE.DirectionalLight(0xffffff, 1.4)
    fill.position.set(-5, 3, 4)
    scene.add(fill)

    let model: THREE.Object3D | null = null
    let animationFrame = 0
    let cancelled = false

    const resize = () => {
      const rect = wrap.getBoundingClientRect()
      const width = Math.max(rect.width, 1)
      const height = Math.max(rect.height, 1)
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }

    const frameModel = (object3D: THREE.Object3D) => {
      const box = new THREE.Box3().setFromObject(object3D)
      const size = new THREE.Vector3()
      const center = new THREE.Vector3()
      box.getSize(size)
      box.getCenter(center)

      object3D.position.x -= center.x
      object3D.position.y -= box.min.y
      object3D.position.z -= center.z

      const maxDim = Math.max(size.x, size.y, size.z) || 1
      const dist = maxDim * 2.6
      camera.position.set(dist * 0.95, dist * 0.68, dist * 1.05)
      camera.lookAt(0, size.y * 0.45, 0)
    }

    new GLTFLoader().load(
      url,
      (gltf) => {
        if (cancelled) return
        model = gltf.scene
        model.traverse((child) => {
          const mesh = child as THREE.Mesh
          if (mesh.isMesh) normalizeMaterial(mesh)
        })
        scene.add(model)
        frameModel(model)
      },
      undefined,
      () => {
        if (!cancelled) wrap.classList.add('model-preview-error')
      },
    )

    const animate = () => {
      animationFrame = requestAnimationFrame(animate)
      if (model) model.rotation.y += 0.007
      renderer.render(scene, camera)
    }

    resize()
    animate()
    window.addEventListener('resize', resize)

    return () => {
      cancelled = true
      cancelAnimationFrame(animationFrame)
      window.removeEventListener('resize', resize)
      if (model) disposeObject3D(model)
      disposeObject3D(scene)
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [url])

  return <div ref={wrapRef} className="model-preview-canvas" aria-hidden="true" />
}
