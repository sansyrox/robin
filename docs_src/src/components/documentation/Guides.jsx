import { Button } from '@/components/documentation/Button'
import { Heading } from '@/components/documentation/Heading'

const guides = [
  {
    href: '/documentation/en/example_app',
    name: 'Getting Started',
    description: 'Learn how to authenticate your API requests.',
  },
  {
    href: '/documentation/en/example_app/authentication',
    name: 'Authentication and Authorization',
    description: 'Understand how to use authentication and authorization.',
  },
  {
    href: '/documentation/en/example_app/authentication-middlewares',
    name: 'Middlewares',
    description:
      'Read about different kinds of Middlewares and how to use them.',
  },
  {
    href: '/documentation/en/example_app/monitoring_and_logging',
    name: 'Monitoring and Logging',
    description: 'Learn how to have montoring and logging in Robyn.',
  },
  {
    href: '/documentation/en/example_app/real_time_notifications',
    name: 'Real Time Notifications',
    description: 'Learn how to have real time notification in Robyn.',
  },
  {
    href: '/documentation/en/example_app/deployment',
    name: 'Deployments',
    description:
      'Learn how to deploy your app to production and manage your deployments.',
  },
  {
    href: '/documentation/en/example_app/openapi',
    name: 'OpenAPI Documentation',
    description: 'Learn how OpenAPI docs are generate for your applications.',
  },
]

export function Guides() {
  return (
    <div className="my-16 xl:max-w-none">
      <Heading level={2} id="guides">
        <h3 className="text-white">Example Application</h3>
      </Heading>
      <div className="not-prose mt-4 grid grid-cols-1 gap-8 border-t  border-white/5 pt-10 sm:grid-cols-2 xl:grid-cols-4">
        {guides.map((guide) => (
          <div key={guide.href}>
            <h3 className="text-sm font-semibold text-white">{guide.name}</h3>
            <p className="mt-1 text-sm text-zinc-400">{guide.description}</p>
            <p className="mt-4">
              <Button href={guide.href} variant="text" arrow="right">
                Read more
              </Button>
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
