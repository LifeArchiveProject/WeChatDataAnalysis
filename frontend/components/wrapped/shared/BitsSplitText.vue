<template>
  <p
    ref="textRef"
    class="bits-split-text inline-block overflow-hidden whitespace-normal"
    :class="className"
    :style="{ textAlign, wordWrap: 'break-word' }"
  >
    {{ text }}
  </p>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText as GSAPSplitText } from 'gsap/SplitText'

const props = defineProps({
  text: { type: String, required: true },
  className: { type: String, default: '' },
  delay: { type: Number, default: 100 },
  duration: { type: Number, default: 0.6 },
  ease: { type: [String, Function], default: 'power3.out' },
  splitType: { type: String, default: 'chars' },
  from: { type: Object, default: () => ({ opacity: 0, y: 32 }) },
  to: { type: Object, default: () => ({ opacity: 1, y: 0 }) },
  threshold: { type: Number, default: 0.1 },
  rootMargin: { type: String, default: '-100px' },
  textAlign: { type: String, default: 'center' },
  onLetterAnimationComplete: { type: Function, default: null }
})

const emit = defineEmits(['animationComplete'])

gsap.registerPlugin(ScrollTrigger, GSAPSplitText)

const textRef = ref(null)
let timeline = null
let scrollTrigger = null
let splitter = null

const cleanup = () => {
  if (timeline) {
    timeline.kill()
    timeline = null
  }
  if (scrollTrigger) {
    scrollTrigger.kill()
    scrollTrigger = null
  }
  if (splitter) {
    splitter.revert()
    splitter = null
  }
}

const createAnimation = async () => {
  if (!import.meta.client || !textRef.value || !props.text) return
  await nextTick()

  const element = textRef.value
  const absoluteLines = props.splitType === 'lines'
  if (absoluteLines) element.style.position = 'relative'

  try {
    splitter = new GSAPSplitText(element, {
      type: props.splitType,
      absolute: absoluteLines,
      linesClass: 'split-line'
    })
  } catch {
    return
  }

  let targets = splitter.chars
  if (props.splitType === 'words') targets = splitter.words
  if (props.splitType === 'lines') targets = splitter.lines
  if (!targets?.length) {
    cleanup()
    return
  }

  targets.forEach((target) => {
    target.style.willChange = 'transform, opacity'
  })

  const startPercent = (1 - props.threshold) * 100
  const marginMatch = /^(-?\d+(?:\.\d+)?)(px|em|rem|%)?$/.exec(props.rootMargin)
  const marginValue = marginMatch ? Number.parseFloat(marginMatch[1]) : 0
  const marginUnit = marginMatch ? marginMatch[2] || 'px' : 'px'
  const sign = marginValue < 0
    ? `-=${Math.abs(marginValue)}${marginUnit}`
    : `+=${marginValue}${marginUnit}`

  timeline = gsap.timeline({
    scrollTrigger: {
      trigger: element,
      start: `top ${startPercent}%${sign}`,
      toggleActions: 'play none none none',
      once: true,
      onToggle: (self) => {
        scrollTrigger = self
      }
    },
    onComplete: () => {
      gsap.set(targets, {
        ...props.to,
        clearProps: 'willChange',
        immediateRender: true
      })
      if (typeof props.onLetterAnimationComplete === 'function') {
        props.onLetterAnimationComplete()
      }
      emit('animationComplete')
    }
  })

  timeline.set(targets, {
    ...props.from,
    immediateRender: false,
    force3D: true
  })

  timeline.to(targets, {
    ...props.to,
    duration: props.duration,
    ease: props.ease,
    stagger: props.delay / 1000,
    force3D: true
  })
}

watch(
  () => [
    props.text,
    props.delay,
    props.duration,
    props.ease,
    props.splitType,
    props.from,
    props.to,
    props.threshold,
    props.rootMargin,
    props.textAlign,
    props.onLetterAnimationComplete
  ],
  async () => {
    cleanup()
    await createAnimation()
  }
)

onMounted(async () => {
  await createAnimation()
})

onBeforeUnmount(() => {
  cleanup()
})
</script>
